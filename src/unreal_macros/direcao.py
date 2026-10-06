"""Direção (v0.0.2, bloco 4): banco de pedidos v0, mapa de capacidades e fila de testes por VALOR.

- Pedido = o que um humano diria em português comum; capacidade = o que o Director precisa saber fazer.
- 'disponivel'/'parcial' só valem se citarem ferramentas MCP que EXISTEM no servidor (não inventar capacidade).
- Fila separa EXPLORAÇÃO (só informação nova; repetir exige justificativa verificável) de REGRESSÃO (casos fixos do
  contrato rodam de novo quando a versão do código muda; nunca são removidos). Usa resultados persistidos
  (relatórios ativos + índice do arquivo), nunca a memória do agente.
"""
import json
import os

from .macros import RAIZ_WORK

DOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "docs")
PEDIDOS = os.path.join(DOCS, "pedidos_v0.json")
CAPACIDADES = os.path.join(DOCS, "capacidades.json")
TRANSVERSAL = "infraestrutura/transversal"
ESTADOS = ("disponivel", "parcial", "inexistente")
MOTIVOS_FILA = ("informacao_nova", "regressao", "confirmacao_correcao", "desempate_hipotese")


def pedidos() -> list:
    return json.load(open(PEDIDOS, encoding="utf-8"))


def ids_pedidos() -> set:
    return {p["id"] for p in pedidos()}


def capacidades() -> dict:
    return {k: v for k, v in json.load(open(CAPACIDADES, encoding="utf-8")).items() if not k.startswith("_")}


def ferramentas_do_servidor() -> set:
    """Nomes das ferramentas MCP declaradas no servidor (lidos do código, não de uma lista à parte)."""
    import ast
    srv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server.py")
    arv = ast.parse(open(srv, encoding="utf-8").read())
    return {n.name for n in arv.body if isinstance(n, ast.FunctionDef)
            and any(getattr(getattr(d, "func", None), "attr", "") == "tool" for d in n.decorator_list)}


def validar() -> list:
    """Problemas do banco/mapa (lista vazia = válido)."""
    erros, caps, tools = [], capacidades(), ferramentas_do_servidor()
    for nome, c in caps.items():
        if c.get("estado") not in ESTADOS:
            erros.append(f"capacidade {nome}: estado inválido {c.get('estado')!r}")
        if c.get("estado") in ("disponivel", "parcial") and not c.get("ferramentas"):
            erros.append(f"capacidade {nome}: '{c['estado']}' sem ferramenta que a sustente")
        if c.get("estado") == "inexistente" and c.get("ferramentas"):
            erros.append(f"capacidade {nome}: inexistente não pode citar ferramentas")
        for f in c.get("ferramentas", []):
            if f not in tools:
                erros.append(f"capacidade {nome}: ferramenta '{f}' não existe no servidor")
    vistos = set()
    for p in pedidos():
        if p["id"] in vistos:
            erros.append(f"pedido {p['id']} duplicado")
        vistos.add(p["id"])
        if p.get("nivel") not in (1, 2):
            erros.append(f"pedido {p['id']}: nível deve ser 1 ou 2")
        for campo in ("texto", "intencao", "criterio", "capacidades"):
            if not p.get(campo):
                erros.append(f"pedido {p['id']}: falta {campo}")
        for c in p.get("capacidades", []):
            if c not in caps:
                erros.append(f"pedido {p['id']}: capacidade '{c}' não existe no mapa")
    return erros


def atendibilidade(pedido_id: str) -> dict:
    """atendivel = todas as capacidades disponíveis; parcial = alguma parcial; nao_atendivel = alguma inexistente."""
    p = next(x for x in pedidos() if x["id"] == pedido_id)
    caps = capacidades()
    estados = {c: caps[c]["estado"] for c in p["capacidades"]}
    if any(e == "inexistente" for e in estados.values()):
        situ = "nao_atendivel"
    elif any(e == "parcial" for e in estados.values()):
        situ = "parcial"
    else:
        situ = "atendivel"
    return {"pedido": pedido_id, "situacao": situ, "capacidades": estados,
            "faltam": sorted(c for c, e in estados.items() if e == "inexistente")}


# ---------- fila de testes por valor ----------
def _chave(macro: str, args=(), kwargs=None) -> str:
    from .macros import _serializavel
    return json.dumps([macro, {"args": _serializavel(list(args)), "kwargs": _serializavel(kwargs or {})}],
                      sort_keys=True, ensure_ascii=False)


def resultados_conhecidos(pasta_relatorios: str = None, indice_arquivo: str = None) -> dict:
    """chave (macro + chamada) -> lista de {versao, ok, id}: relatórios ativos + índice do arquivo morto."""
    import glob
    pasta_relatorios = pasta_relatorios or os.path.join(RAIZ_WORK, "relatorios")
    indice_arquivo = indice_arquivo or os.path.join(RAIZ_WORK, "relatorios_arquivo", "indice.jsonl")
    out = {}

    def add(rel):
        if rel.get("macro") and "chamada" in rel:
            k = json.dumps([rel["macro"], rel["chamada"]], sort_keys=True, ensure_ascii=False)
            out.setdefault(k, []).append({"versao": (rel.get("ambiente") or {}).get("versao_codigo"),
                                          "ok": rel.get("ok"), "id": rel.get("id")})
    for arq in glob.glob(os.path.join(pasta_relatorios, "*.json")):
        try:
            add(json.load(open(arq, encoding="utf-8")))
        except (OSError, ValueError):
            pass
    if os.path.exists(indice_arquivo):
        for linha in open(indice_arquivo, encoding="utf-8"):
            if linha.strip():
                add(json.loads(linha))
    return out


def montar_fila(casos: list, versao: str, conhecidos: dict, justificativas: dict = None,
                referencias_validas=lambda ref: False) -> dict:
    """casos: [{id, tipo: contrato|exploracao, macro, args, kwargs}]. justificativas: {id: {motivo, referencia}}.
    Devolve fila (com motivo), excluídos (com o resultado já conhecido) e contrato em dia (mantido, não removido)."""
    justificativas = justificativas or {}
    fila, excluidos, em_dia = [], [], []
    for c in casos:
        hist = conhecidos.get(_chave(c["macro"], c.get("args", ()), c.get("kwargs")), [])
        nesta = [h for h in hist if h["versao"] == versao]
        if c["tipo"] == "contrato":
            (em_dia if nesta else fila).append(dict(c, motivo="regressao") if not nesta else
                                               dict(c, situacao="em_dia", ultimo=nesta[-1]["id"]))
            continue
        if not nesta:
            fila.append(dict(c, motivo="informacao_nova", nota="código mudou desde o último resultado" if hist else ""))
            continue
        j = justificativas.get(c["id"])
        if j and j.get("motivo") in ("confirmacao_correcao", "desempate_hipotese") and referencias_validas(j.get("referencia")):
            fila.append(dict(c, motivo=j["motivo"], referencia=j["referencia"]))
        else:
            motivo = "resultado já conhecido nesta versão do código"
            if j:
                motivo += f"; justificativa recusada ({j.get('motivo')!r} exige referência verificável)"
            excluidos.append(dict(c, motivo_exclusao=motivo, conhecido=nesta[-1]["id"]))
    return {"fila": fila, "excluidos": excluidos, "contrato_em_dia": em_dia}
