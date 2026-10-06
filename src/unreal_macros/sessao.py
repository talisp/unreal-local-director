"""Passagem de bastão entre sessões (v0.0.2, bloco 4). A sessão nova continua pelo ESTADO PERSISTIDO, não pela
memória da anterior. Só o necessário (cabe em poucos KB): objetivo, experimentos abertos, último progresso útil,
degraus, pendências, lições relevantes, bloqueios/esperas ativos. Leitura pura: não escreve alarmes nem PAUSA."""
import datetime as dt
import glob
import json
import os
import time

from . import emperramento as E
from .macros import RAIZ_WORK

TAMANHO_MAX = 4000


def _pausa(pasta_sup):
    arq = os.path.join(pasta_sup, "PAUSA")
    if not os.path.exists(arq):
        return None
    try:
        return json.load(open(arq, encoding="utf-8"))
    except (OSError, ValueError):
        return {"motivo": "arquivo PAUSA ilegível (tratado como pausa)"}


def _pasta(p):
    return p or os.path.join(RAIZ_WORK, "sessao")


def definir_objetivo(texto: str, pedido: str = "", pasta: str = None) -> dict:
    if len(str(texto).strip()) < 10:
        raise ValueError("objetivo vazio ou curto demais")
    pasta = _pasta(pasta)
    os.makedirs(pasta, exist_ok=True)
    obj = {"texto": texto.strip(), "pedido": pedido, "quando": dt.datetime.now().isoformat(timespec="seconds")}
    json.dump(obj, open(os.path.join(pasta, "objetivo.json"), "w", encoding="utf-8"), ensure_ascii=False)
    return obj


def passagem(agora: float = None, pasta_rel: str = None, pasta_exp: str = None, pasta_sessao: str = None,
             trava_path: str = None, pasta_sup: str = None, pasta_licoes: str = None) -> dict:
    from . import experimentos as X
    from . import resolver as RS
    from . import supervisor as S
    from .macros import TRAVA, pausa_ativa
    agora = agora or time.time()
    pasta_rel = pasta_rel or os.path.join(RAIZ_WORK, "relatorios")
    pasta_exp = pasta_exp or X.PASTA
    arq_obj = os.path.join(_pasta(pasta_sessao), "objetivo.json")
    objetivo = json.load(open(arq_obj, encoding="utf-8")) if os.path.exists(arq_obj) else None
    itens = E.carregar_historico(pasta_rel, pasta_exp)
    abertos = []
    for arq in glob.glob(os.path.join(pasta_exp, "*.json")):
        e = json.load(open(arq, encoding="utf-8"))
        if e.get("estado") == "aberto":
            est = E.avaliar(itens, e["nome"])
            abertos.append({"nome": e["nome"], "tipo": e["tipo"], "pedido": e.get("pedido"), "corridas": len(e["corridas"]),
                            "restante_min": round(max(0, e["limite_min"] * 60 - (agora - e["inicio"])) / 60),
                            "degrau": est["degrau"], "emperrado": est["emperrado"]})
    sup = S.avaliar(agora, pasta_rel, pasta_exp, trava_path=trava_path or TRAVA, pasta_sup=pasta_sup, registrar=False)
    licoes = []
    for linha in sorted({a["nome"] for a in abertos if a["emperrado"]} | ({"*"} if sup["sessao"]["emperrado"] else set())):
        est = E.avaliar_sessao(itens) if linha == "*" else E.avaliar(itens, linha)
        o = RS.orientar(est, pasta_licoes)
        licoes += [{"id": l["id"], "acao": l["acao"]} for l in o.get("licoes", []) if l["id"] not in {x["id"] for x in licoes}]
    pend_licoes = []
    arq_ap = os.path.join(pasta_licoes or RS.PASTA_LICOES, "aplicacoes.jsonl")
    if os.path.exists(arq_ap):
        resolvidas = set(RS.carregar_votos(pasta_licoes).get("_resolvidas", []))
        pend_licoes = [json.loads(l)["aplicacao"] for l in open(arq_ap, encoding="utf-8") if l.strip()
                       and json.loads(l)["aplicacao"] not in resolvidas]
    st = __import__("unreal_macros.trava", fromlist=["estado"]).estado(trava_path or TRAVA)
    out = {
        "objetivo": objetivo,
        "experimentos_abertos": abertos,
        "ultimo_progresso": sup["ultimo_progresso"],
        "sem_progresso_min": sup["sem_progresso_min"],
        "degrau_sessao": sup["sessao"]["degrau"],
        "pendencias": {"experimentos_abertos": [a["nome"] for a in abertos], "licoes_sem_voto": pend_licoes[-5:],
                       "alarmes": sorted({a["tipo"] for a in sup["alarmes"]})},
        "licoes_relevantes": licoes[:3],
        "bloqueios": {"pausa": _pausa(pasta_sup) if pasta_sup else pausa_ativa(),
                      "trava": st["estado"] if st["estado"] != "livre" else None},
        "esperas_ativas": sup["esperas_ativas"],
    }
    texto = json.dumps(out, ensure_ascii=False, default=str)
    if len(texto) > TAMANHO_MAX:  # nunca despejar histórico: corta listas longas, mantém o essencial
        out["experimentos_abertos"] = out["experimentos_abertos"][:5]
        out["esperas_ativas"] = out["esperas_ativas"][:3]
        out["truncado"] = True
    return out
