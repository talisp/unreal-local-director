"""Supervisor mínimo (v0.0.2, bloco 4). Observa SÓ eventos das ferramentas; não destrói nada.

A. vida/travamento: trava com dono morto (recomenda liberar_trava_orfa) ou dono vivo segurando a trava há muito
   tempo sem nenhum relatório novo (macro presa: recomenda conserto);
B. 45 min sem PROGRESSO ÚTIL (descontadas as esperas declaradas). Progresso útil = melhora medida, RESULTADO NOVO
   (ação+resultado+erro+estado nunca visto na sessão, ignorando o alvo: falhar o mesmo gate com outro clipe não é
   novidade), mudança REAL de degrau, experimento fechado. Não contam: texto, chamadas repetidas, renomear experimento,
   nova hipótese só escrita, escalada (ela SUSPENDE o relógio como espera humana, mas não o renova);
C. violações (produção alterada, guarda.py do sandbox alterada, tentativa proibida recusada): escreve a PAUSA;
D. emperramento de SESSÃO (mesma estratégia com nomes diferentes de experimento).
Cada alarme é registrado de forma determinística e idempotente com motivo, último progresso, evidência e ação.
"""
import datetime as dt
import hashlib
import json
import os
import subprocess

from . import emperramento as E
from . import trava as T
from .macros import RAIZ_WORK

LIMITE_MIN = 45
MACRO_PRESA_MIN = 30
ESPERA_TRAVA_MIN = 10


def _ts_evento(ev):
    return dt.datetime.fromisoformat(ev["quando"]).timestamp() if ev.get("quando") else 0.0


def _eventos_brutos(pasta_exp):
    arq = os.path.join(pasta_exp, "eventos.jsonl")
    return [json.loads(l) for l in open(arq, encoding="utf-8") if l.strip()] if os.path.exists(arq) else []


def progressos_uteis(itens: list, brutos: list) -> list:
    """Eventos de progresso útil, só de ferramentas: [(quando, tipo, ref)]."""
    out, vistos = [], set()
    for t in itens:  # resultado novo (alvo ignorado)
        if t["tipo"] == "tentativa":
            k = E._canon([t["acao"], t["resultado"], t["erro"], t["estado"]])
            if k not in vistos:
                vistos.add(k)
                out.append((t["quando"], "resultado_novo", t["ref"]))
    linhas = {t.get("linha") for t in itens if t.get("linha")}
    for linha in linhas:
        est = E.avaliar(itens, linha)
        degrau_ant = None
        for m in est["marcos"]:
            if m["tipo"] == "progresso":
                out.append((m["quando"], "melhora_medida", m["ref"]))
                degrau_ant = None
        for d, m in zip(est["disparos"], [x for x in est["marcos"] if x["tipo"] == "disparo"]):
            if d["degrau"] != degrau_ant:  # só mudança REAL de degrau
                out.append((m["quando"], f"degrau:{d['degrau']}", m["ref"]))
            degrau_ant = d["degrau"]
    for ev in brutos:
        if ev.get("evento") == "fechado":
            out.append((_ts_evento(ev), "experimento_fechado", ev.get("experimento")))
    return sorted(out)


def _esperas(itens: list, brutos: list, agora: float):
    """Intervalos de espera declarada [(ini, fim)] e as esperas ATIVAS agora."""
    intervalos, ativas = [], []
    abertas, prazos = {}, {}
    prazo_ev = {(ev.get("experimento"), ev.get("n")): ev.get("prazo_s") for ev in brutos if ev.get("evento") == "corrida_iniciada"}
    for t in itens:
        if t["tipo"] == "espera" and t.get("espera") == "corrida":
            abertas[(t.get("linha"), t.get("corrida"))] = t["quando"]
            prazos[(t.get("linha"), t.get("corrida"))] = prazo_ev.get((t.get("linha"), t.get("corrida")))
        elif t["tipo"] == "tentativa" and (t.get("linha"), t.get("corrida")) in abertas:
            intervalos.append((abertas.pop((t.get("linha"), t.get("corrida"))), t["quando"]))
        elif t["tipo"] == "espera" and t.get("espera") in ("trava", "pausa"):
            # bloco 5 (dado real): a espera acaba na PRÓXIMA tentativa (antes: 10 min fixos escondiam o relógio)
            depois = [x["quando"] for x in itens if x["tipo"] == "tentativa" and x["quando"] > t["quando"]]
            fim = min([agora, t["quando"] + ESPERA_TRAVA_MIN * 60] + depois[:1])
            intervalos.append((t["quando"], fim))
            if not depois and agora - t["quando"] < ESPERA_TRAVA_MIN * 60:
                ativas.append({"tipo": t["espera"], "ref": t["ref"]})
    perdidas = []
    for (linha, n), ini in abertas.items():
        # bloco 5 (falha provocada): corrida aberta além do prazo que ELA declarou (+60 s) não é espera — o processo
        # morreu ou travou; tratar como espera para sempre esconderia o problema
        limite = ini + float(prazos.get((linha, n)) or 1500) + 60
        if agora > limite:
            intervalos.append((ini, limite))
            perdidas.append({"linha": linha, "corrida": n, "desde": ini})
            continue
        intervalos.append((ini, agora))
        ativas.append({"tipo": "corrida", "linha": linha, "corrida": n})
    tentativas = [t for t in itens if t["tipo"] == "tentativa"]
    for ev in brutos:
        if ev.get("evento") == "escalada":
            ini = _ts_evento(ev)
            depois = [t["quando"] for t in tentativas if t["quando"] > ini]
            fim = min(depois) if depois else agora
            intervalos.append((ini, fim))
            if not depois:
                ativas.append({"tipo": "humano", "linha": ev.get("experimento"), "motivo": ev.get("motivo")})
    _esperas.perdidas = perdidas
    return intervalos, ativas


def _tempo_em_espera(intervalos, ini, fim):
    total, cursor = 0.0, ini
    for a, b in sorted(intervalos):
        a, b = max(a, cursor), min(b, fim)
        if b > a:
            total += b - a
            cursor = b
    return total


def _violacoes(brutos, hashes_producao, base_producao, sandbox, guarda_sha_base):
    out = []
    if hashes_producao and os.path.exists(hashes_producao):
        r = subprocess.run(["sha256sum", "-c", "--quiet", hashes_producao], cwd=base_producao, capture_output=True, text=True)
        if r.returncode:
            out.append({"tipo": "producao_alterada", "evidencia": (r.stdout + r.stderr).strip().splitlines()[:5]})
    if sandbox and guarda_sha_base:
        g = subprocess.run(["git", "-C", sandbox, "show", "master:src/unreal_macros/guarda.py"], capture_output=True,
                           text=True, encoding="utf-8")
        if g.returncode or hashlib.sha256(g.stdout.encode("utf-8")).hexdigest() != guarda_sha_base:
            out.append({"tipo": "guarda_alterada", "evidencia": ["sandbox master: src/unreal_macros/guarda.py"]})
    for ev in brutos:
        if ev.get("evento") == "recusa" and any(s in ev.get("motivo", "") for s in ("ALTERADA", "proibido")):
            out.append({"tipo": "tentativa_proibida", "evidencia": [ev.get("experimento"), ev.get("motivo")]})
    return out


ACAO = {
    "trava_orfa": "chamar liberar_trava_orfa (o dono morreu)",
    "corrida_perdida": "a corrida passou do prazo sem resultado: tratar como falha (não como sucesso), fechar o experimento e avisar",
    "macro_presa": "conserto: confirmar o processo dono com o operador; não repetir a macro",
    "atividade_sem_progresso": "parar a linha atual; consultar_emperramento e seguir o degrau; ou trocar de papel/tarefa",
    "sem_atividade": "verificar se o agente está vivo; reiniciar sessão pela passagem de bastão",
    "producao_alterada": "PAUSA: operador confere o que mudou na produção",
    "guarda_alterada": "PAUSA: operador confere a guarda do sandbox",
    "tentativa_proibida": "PAUSA: operador revê a tentativa recusada",
    "emperramento_de_sessao": "seguir o degrau da sessão (resolver-problemas): a estratégia se repete sob nomes diferentes",
}


def avaliar(agora: float, pasta_rel: str = None, pasta_exp: str = None, trava_path: str = None, hashes_producao: str = None,
            base_producao: str = None, sandbox: str = None, guarda_sha_base: str = None, pasta_sup: str = None,
            inicio_observacao: float = None, registrar: bool = True) -> dict:
    from . import experimentos as X
    from .macros import TRAVA
    pasta_rel = pasta_rel or os.path.join(RAIZ_WORK, "relatorios")
    pasta_exp = pasta_exp or X.PASTA
    pasta_sup = pasta_sup or os.path.join(RAIZ_WORK, "supervisor")
    itens = E.carregar_historico(pasta_rel, pasta_exp)
    brutos = _eventos_brutos(pasta_exp)
    prog = progressos_uteis(itens, brutos)
    intervalos, ativas = _esperas(itens, brutos, agora)
    inicio = inicio_observacao if inicio_observacao is not None else (itens[0]["quando"] if itens else agora)
    ultimo = prog[-1] if prog else None
    desde = max(ultimo[0], inicio) if ultimo else inicio
    sem_prog_min = max(0.0, (agora - desde - _tempo_em_espera(intervalos, desde, agora)) / 60)
    alarmes = []
    for p in getattr(_esperas, "perdidas", []):
        alarmes.append({"tipo": "corrida_perdida", "evidencia": [f"{p['linha']}#corrida#{p['corrida']}"]})
    # A. vida / travamento
    st = T.estado(trava_path or TRAVA)
    if st["estado"] == "morta":
        alarmes.append({"tipo": "trava_orfa", "evidencia": [st["motivo"]]})
    elif st["estado"] == "viva" and st["info"]:
        desde_trava = float(st["info"].get("desde") or agora)
        rel_depois = [t for t in itens if t["fonte"] == "relatorio" and t["quando"] >= desde_trava]
        if (agora - desde_trava) / 60 >= MACRO_PRESA_MIN and not rel_depois and not [a for a in ativas if a["tipo"] == "corrida"]:
            alarmes.append({"tipo": "macro_presa", "evidencia": [st["motivo"], f"trava há {(agora - desde_trava) / 60:.0f} min"]})
    # B. sem progresso útil
    if not ativas and sem_prog_min >= LIMITE_MIN:
        atividade = [t for t in itens if t["tipo"] == "tentativa" and t["quando"] > desde]
        alarmes.append({"tipo": "atividade_sem_progresso" if atividade else "sem_atividade",
                        "evidencia": [t["ref"] for t in atividade[-5:]] or [f"{sem_prog_min:.0f} min sem eventos"]})
    # C. violações
    viol = _violacoes(brutos, hashes_producao, base_producao, sandbox, guarda_sha_base)
    alarmes += viol
    # D. emperramento de sessão que escapa das linhas
    ses = E.avaliar_sessao(itens)
    if ses["emperrado"]:
        linhas_ev = {t.get("linha") for t in itens if t.get("ref") in set(ses["ultimo_disparo"]["evidencia"])}
        if len(linhas_ev) > 1 or not any(E.avaliar(itens, l)["emperrado"] for l in linhas_ev):
            alarmes.append({"tipo": "emperramento_de_sessao", "evidencia": ses["ultimo_disparo"]["evidencia"],
                            "degrau": ses["degrau"], "linhas": sorted(x for x in linhas_ev if x)})
    for a in alarmes:
        a["motivo"] = a["tipo"]
        a["acao_recomendada"] = ACAO[a["tipo"]]
        a["ultimo_progresso"] = {"quando": ultimo[0], "tipo": ultimo[1], "ref": ultimo[2]} if ultimo else None
    pausa = None
    if viol and registrar:
        pausa = {"motivo": "; ".join(v["tipo"] for v in viol), "quando": dt.datetime.now().isoformat(timespec="seconds")}
        os.makedirs(pasta_sup, exist_ok=True)
        if not os.path.exists(os.path.join(pasta_sup, "PAUSA")):
            json.dump(pausa, open(os.path.join(pasta_sup, "PAUSA"), "w", encoding="utf-8"), ensure_ascii=False)
    if registrar:
        _registrar(alarmes, pasta_sup)
    return {"agora": agora, "ultimo_progresso": alarmes[0]["ultimo_progresso"] if alarmes else
            ({"quando": ultimo[0], "tipo": ultimo[1], "ref": ultimo[2]} if ultimo else None),
            "sem_progresso_min": round(sem_prog_min, 1), "esperas_ativas": ativas, "alarmes": alarmes, "pausa": pausa,
            "sessao": {"emperrado": ses["emperrado"], "degrau": ses["degrau"]}}


def _registrar(alarmes, pasta_sup):
    if not alarmes:
        return
    os.makedirs(pasta_sup, exist_ok=True)
    arq = os.path.join(pasta_sup, "alarmes.jsonl")
    vistos = {json.loads(l)["chave"] for l in open(arq, encoding="utf-8") if l.strip()} if os.path.exists(arq) else set()
    with open(arq, "a", encoding="utf-8") as f:
        for a in alarmes:
            chave = a["tipo"] + "|" + json.dumps(a["evidencia"], ensure_ascii=False, sort_keys=True)
            if chave not in vistos:
                f.write(json.dumps(dict(a, chave=chave, registrado=dt.datetime.now().isoformat(timespec="seconds")),
                                   ensure_ascii=False) + "\n")
                vistos.add(chave)
