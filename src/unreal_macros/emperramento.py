"""Detector de emperramento (v0.0.2, bloco 3). Lê SÓ registros das ferramentas — relatórios de macro
(work/relatorios/*.json) e eventos do controlador (work/experimentos/eventos.jsonl) — nunca texto livre do agente.

Cada registro vira uma TENTATIVA com assinatura normalizada:
    (ação, alvo, resultado, classe do erro, estado relevante)
e sem campos voláteis (hora, duração, nº de chamadas, ids, caminhos, valores medidos, avisos, contexto).

Regras (definidas em "repetições equivalentes"; nenhuma passa de 2):
  repeticao    — a mesma assinatura 2 vezes seguidas, a 2ª sem sucesso (dispara na 2ª);
  vai_e_volta  — A, B, A, B (dispara no 4º = 2ª repetição do par);
  mesmo_erro   — a mesma classe de erro 2 vezes seguidas com ações/alvos diferentes (dispara na 2ª);
  estagnacao   — 3 tentativas diferentes, todas sem sucesso e com o MESMO estado (dispara na 3ª = 2ª repetição do estado).
Esperas declaradas pela ferramenta (trava ocupada, corrida em andamento) não contam. Progresso = MELHORA medida
(falha -> sucesso, menos gates reprovados, mais testes ok): zera a escada. Registro incompleto não entra em
comparação nenhuma (sem conclusão inventada).
Cada disparo sobe um degrau da escada: cutucar -> replanejar -> outro_caminho -> escalar -> abortar.
"""
import datetime as dt
import glob
import json
import os
import re

DEGRAUS = ("cutucar", "replanejar", "outro_caminho", "escalar", "abortar")
PRIORIDADE = ("repeticao", "vai_e_volta", "mesmo_erro", "estagnacao")


# ---------- normalização ----------
def _quando_do_id(rid: str) -> float:
    try:
        return dt.datetime.strptime(rid[:15], "%Y%m%d-%H%M%S").timestamp()
    except (ValueError, TypeError):
        return 0.0


def _canon(o) -> str:
    return json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _classe_bloqueio(bloq: str) -> str:
    """Classe do erro = tipo da exceção (texto antes do ':'), sem números nem detalhes variáveis."""
    cabeca = bloq.split(":", 1)[0].strip()
    return re.sub(r"\d+", "#", cabeca)[:60]


def de_relatorio(rel: dict) -> dict:
    """Relatório de macro (formato do envelope, bloco 1 + alvo/espera do bloco 3) -> tentativa normalizada."""
    t = {"fonte": "relatorio", "ref": rel.get("id"), "quando": rel.get("quando_ts") or _quando_do_id(rel.get("id", "")),
         "linha": (rel.get("contexto") or {}).get("linha") or rel.get("macro"), "acao": rel.get("macro")}
    if rel.get("espera"):
        return dict(t, tipo="espera", espera=rel["espera"].get("tipo"))
    if "chamada" not in rel or rel.get("macro") is None or "ok" not in rel:
        return dict(t, tipo="incompleta", falta=[k for k in ("chamada", "macro", "ok") if k not in rel or rel.get(k) is None])
    gates = rel.get("medidas", {}).get("gates") or []
    falhos = sorted(g["nome"] for g in gates if g.get("resultado") != "PASS")
    ok = bool(rel["ok"])
    if ok:
        erro = None
    elif falhos:
        erro = "gate:" + ",".join(falhos)
    else:
        erro = _classe_bloqueio(rel.get("bloqueio") or "falha")
    return dict(t, tipo="tentativa", alvo=_canon(rel["chamada"]), resultado="ok" if ok else "falha", erro=erro,
                estado={"ok": ok, "falhos": falhos}, nota_progresso=(0 if ok else 1, len(falhos)))


def de_evento(ev: dict) -> dict | None:
    """Evento do controlador de experimentos (bloco 2) -> tentativa normalizada (ou marcador)."""
    quando = dt.datetime.fromisoformat(ev["quando"]).timestamp() if ev.get("quando") else 0.0
    base = {"fonte": "experimento", "ref": f"{ev.get('experimento')}#{ev.get('evento')}#{ev.get('n', '')}", "quando": quando,
            "linha": ev.get("experimento")}
    tipo = ev.get("evento")
    if tipo == "corrida_iniciada":
        return dict(base, tipo="espera", espera="corrida", acao="rodar_experimento", corrida=ev.get("n"))
    if tipo == "corrida":
        if "script" not in ev:
            return dict(base, tipo="incompleta", falta=["script"])
        ok = ev.get("codigo_saida") == 0
        erro = None if ok else ("tempo_esgotado" if ev.get("estourou_tempo") else f"saida:{ev.get('codigo_saida')}")
        tok = ev.get("testes_ok")
        nota = (0 if ok else 1, -(tok[0] / tok[1]) if tok and tok[1] else 0)
        return dict(base, tipo="tentativa", acao="rodar_experimento", alvo=ev["script"], resultado="ok" if ok else "falha",
                    erro=erro, estado={"ok": ok, "testes_ok": tok}, nota_progresso=nota, corrida=ev.get("n"))
    if tipo == "recusa" and str(ev.get("motivo", "")).startswith("PAUSADO"):
        return dict(base, tipo="espera", espera="pausa", acao=f"recusa:{ev.get('acao')}")
    if tipo == "recusa":
        motivo = re.sub(r"\d+", "#", ev.get("motivo", ""))[:80]
        return dict(base, tipo="tentativa", acao=f"recusa:{ev.get('acao')}", alvo=motivo, resultado="falha",
                    erro=f"recusa:{ev.get('acao')}", estado={"ok": False, "recusa": motivo}, nota_progresso=(1, 0))
    if tipo in ("iniciado", "fechado"):
        return dict(base, tipo=tipo)
    return None


def assinatura(t: dict) -> str:
    return _canon([t["acao"], t["alvo"], t["resultado"], t["erro"], t["estado"]])


# ---------- leitura ----------
def carregar_historico(pasta_relatorios: str, pasta_experimentos: str) -> list:
    """Todas as tentativas/esperas/marcadores, em ordem de tempo, lidas dos registros das ferramentas."""
    itens = []
    for arq in glob.glob(os.path.join(pasta_relatorios, "*.json")):
        try:
            itens.append(dict(de_relatorio(json.load(open(arq, encoding="utf-8"))), ordem=os.path.basename(arq)))
        except (OSError, ValueError):
            itens.append({"fonte": "relatorio", "ref": os.path.basename(arq), "tipo": "incompleta", "falta": ["json"],
                          "quando": 0.0, "linha": None})
    ev_arq = os.path.join(pasta_experimentos, "eventos.jsonl")
    if os.path.exists(ev_arq):
        for i, linha in enumerate(open(ev_arq, encoding="utf-8")):
            if linha.strip():
                t = de_evento(json.loads(linha))
                if t:
                    itens.append(dict(t, ordem=f"{i:09d}"))
    # mesmo segundo: vale a ORDEM DO ARQUIVO dentro de cada fonte (06/10: corrida_iniciada e corrida no mesmo segundo
    # foram invertidas pela referência e a corrida parecia ainda rodando)
    return sorted(itens, key=lambda t: (t["quando"], t["fonte"], t.get("ordem") or ""))


# ---------- detecção ----------
def _regras(h: list) -> str | None:
    """h = tentativas válidas desde o último disparo/progresso (mais recente por último)."""
    falhou = not h[-1]["estado"].get("ok")  # repetir o que DEU CERTO (consulta, checagem) não é emperramento
    if falhou and len(h) >= 2 and assinatura(h[-1]) == assinatura(h[-2]):
        return "repeticao"
    if len(h) >= 4 and not all(x["estado"].get("ok") for x in h[-4:]):
        s = [assinatura(x) for x in h[-4:]]
        if s[0] == s[2] and s[1] == s[3] and s[0] != s[1]:
            return "vai_e_volta"
    if len(h) >= 2 and h[-1]["erro"] and h[-1]["erro"] == h[-2]["erro"]:
        return "mesmo_erro"
    if len(h) >= 3:
        u = h[-3:]
        if not any(x["estado"].get("ok") for x in u) and len({assinatura(x) for x in u}) == 3 \
                and len({_canon(x["estado"]) for x in u}) == 1:
            return "estagnacao"
    return None


def avaliar(itens: list, linha: str) -> dict:
    """Estado determinístico da linha: disparos, degrau atual, esperas e incompletos. Função pura dos registros."""
    h, disparos, n_disp, esperas, incompletos, progressos, ultima = [], [], 0, [], [], 0, None
    historico_acao, marcos = {}, []
    corridas_abertas = set()
    for t in itens:
        if t.get("linha") != linha:
            continue
        if t["tipo"] == "espera":
            esperas.append(t["ref"])
            if t.get("espera") == "corrida":
                corridas_abertas.add(t.get("corrida"))
            continue
        if t["tipo"] == "incompleta":
            incompletos.append({"ref": t["ref"], "falta": t["falta"]})
            continue
        if t["tipo"] in ("iniciado", "fechado"):
            if t["tipo"] == "iniciado":
                h, n_disp, historico_acao = [], 0, {}
            else:
                h = []
            continue
        corridas_abertas.discard(t.get("corrida"))
        mesma_acao = [x["nota_progresso"] for x in historico_acao.get(t["acao"], [])]
        if mesma_acao and t["nota_progresso"] < min(mesma_acao):  # melhora medida sobre a melhor anterior da MESMA ação
            progressos += 1
            h, n_disp = [], 0
            marcos.append({"tipo": "progresso", "quando": t["quando"], "ref": t["ref"]})
        historico_acao.setdefault(t["acao"], []).append(t)
        h.append(t)
        ultima = t
        tipo = _regras(h)
        if tipo:
            n_disp += 1
            janela = h[-4:] if tipo == "vai_e_volta" else (h[-3:] if tipo == "estagnacao" else h[-2:])
            disparos.append({"tipo": tipo, "degrau": DEGRAUS[min(n_disp, len(DEGRAUS)) - 1],
                             "assinaturas": [assinatura(x) for x in janela], "evidencia": [x["ref"] for x in janela],
                             "erro": t["erro"], "acao": t["acao"]})
            marcos.append({"tipo": "disparo", "quando": t["quando"], "ref": t["ref"]})
            h = []
    degrau = _degrau_atual(disparos, marcos)
    # bloco 5 (dado real): emperrado = degrau ATIVO (houve disparo e nenhum progresso depois). Antes, qualquer
    # tentativa posterior (até de outra linha, na visão de sessão) apagava o emperramento.
    return {"linha": linha, "emperrado": degrau is not None,
            "ultimo_disparo": disparos[-1] if disparos else None, "disparos": disparos,
            "degrau": degrau, "progressos": progressos,
            "esperando": sorted(x for x in corridas_abertas if x is not None), "esperas": len(esperas),
            "incompletos": incompletos, "marcos": marcos}


def _degrau_atual(disparos, marcos):
    """Degrau vigente: o do último disparo, a menos que tenha havido PROGRESSO depois dele (aí a escada zerou)."""
    if not disparos:
        return None
    ultimo = [m for m in marcos if m["tipo"] in ("disparo", "progresso")][-1]
    return disparos[-1]["degrau"] if ultimo["tipo"] == "disparo" else None


def registrar_disparos(estado: dict, arquivo: str):
    """Grava os disparos novos (idempotente: chave = linha + evidência)."""
    vistos = set()
    if os.path.exists(arquivo):
        vistos = {json.loads(l)["chave"] for l in open(arquivo, encoding="utf-8") if l.strip()}
    os.makedirs(os.path.dirname(arquivo) or ".", exist_ok=True)
    with open(arquivo, "a", encoding="utf-8") as f:
        for d in estado["disparos"]:
            chave = estado["linha"] + "|" + "|".join(str(e) for e in d["evidencia"])
            if chave not in vistos:
                f.write(json.dumps({"chave": chave, "linha": estado["linha"], **d,
                                    "quando": dt.datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False) + "\n")
                vistos.add(chave)


def avaliar_sessao(itens: list) -> dict:
    """Visão da SESSÃO inteira (bloco 4): ignora a linha e os marcadores iniciado/fechado. Pega a mesma estratégia
    repetida sob NOMES DIFERENTES de experimento (cada linha isolada teria uma tentativa só)."""
    sessao = [dict(t, linha="*") for t in itens if t["tipo"] not in ("iniciado", "fechado")]
    return avaliar(sessao, "*")
