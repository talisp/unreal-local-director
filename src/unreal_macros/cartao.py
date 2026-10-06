"""Cartão de cena: o plano que o Hermes escreve. Só conceitos das macros (atores, clipes, ordem, 'deve evitar');
sem quadros de animação e sem nomes de API do Unreal. O executor valida e roda passo a passo."""
import jsonschema

from . import catalogo, workflows
from . import macros as M

ACOES = {
    "aplicar_clipe": lambda p: M.aplicar_clipe(p["ator"], p["clipe"], loop=p.get("loop", True), tempo=p.get("tempo", 0.0)),
    "plateia_em_loop": lambda p: workflows.plateia_em_loop(p["atores"], texto=p.get("texto", "idle talking conversation"),
                                                           candidatos=p.get("candidatos")),
    "medir_personagem": lambda p: M.medir_personagem(p["ator"]),
    "capturar_evidencia": lambda p: M.capturar_evidencia(p["ator"], vista=p.get("vista", "frontal")),
}

SCHEMA = {
    "type": "object",
    "required": ["objetivo", "passos"],
    "properties": {
        "objetivo": {"type": "string", "minLength": 5},
        "deve_evitar": {"type": "array", "items": {"type": "string"}},
        "passos": {"type": "array", "minItems": 1, "items": {
            "type": "object", "required": ["id", "acao"],
            "properties": {
                "id": {"type": "string"},
                "acao": {"enum": sorted(ACOES)},
                "ator": {"type": "string"}, "atores": {"type": "array", "items": {"type": "string"}},
                "clipe": {"type": "string"}, "candidatos": {"type": "array", "items": {"type": "string"}},
                "texto": {"type": "string"}, "loop": {"type": "boolean"}, "tempo": {"type": "number"},
                "vista": {"enum": ["frontal", "lateral", "traseira"]},
                "depois": {"type": "string"}}}}},
}


@M.macro
def validar_cartao(rel, cartao: dict):
    """Confere o cartão sem executar: formato, ids únicos, 'depois' apontando para passo anterior, atores existentes
    e clipes existentes na biblioteca."""
    erros = []
    for e in jsonschema.Draft7Validator(SCHEMA).iter_errors(cartao):
        erros.append(f"formato ({'/'.join(str(x) for x in e.path) or 'raiz'}): {e.message}")
    vistos = set()
    nomes_biblio = {it["nome"] for it in catalogo._indice()}
    exige = {"aplicar_clipe": ("ator", "clipe"), "medir_personagem": ("ator",), "capturar_evidencia": ("ator",),
             "plateia_em_loop": ("atores",)}
    for p in cartao.get("passos", []):
        for campo in exige.get(p.get("acao"), ()):
            if not p.get(campo):
                erros.append(f"{p.get('id')}: ação {p.get('acao')} exige '{campo}'")
    for p in cartao.get("passos", []):
        if p.get("id") in vistos:
            erros.append(f"id repetido: {p.get('id')}")
        if p.get("depois") and p["depois"] not in vistos:
            erros.append(f"{p.get('id')}: 'depois' aponta para passo inexistente ou posterior ({p['depois']})")
        vistos.add(p.get("id"))
        for at in ([p["ator"]] if p.get("ator") else []) + p.get("atores", []):
            try:
                M.resolver_ator(at)
            except ValueError:
                erros.append(f"{p.get('id')}: ator não existe ({at})")
        for cl in ([p["clipe"]] if p.get("clipe") else []) + p.get("candidatos", []):
            if not cl.startswith("/Game/") and cl not in nomes_biblio:
                erros.append(f"{p.get('id')}: clipe não está na biblioteca ({cl})")
    rel["medidas"]["erros"] = erros
    if erros:
        rel["bloqueio"] = f"{len(erros)} erro(s) no cartão"


@M.macro
def executar_cartao(rel, cartao: dict):
    """Valida e executa o cartão em ordem; para no primeiro passo que falhar (política, regra 8)."""
    v = validar_cartao(cartao)
    if not v["ok"]:
        rel["bloqueio"] = "cartão inválido: " + "; ".join(v["medidas"]["erros"][:5])
        return
    feitos = []
    for p in cartao["passos"]:
        r = ACOES[p["acao"]](p)
        feitos.append({"id": p["id"], "acao": p["acao"], "ok": r["ok"], "bloqueio": r["bloqueio"], "evidencias": r["evidencias"]})
        rel["evidencias"] += r["evidencias"]
        if not r["ok"]:
            rel["bloqueio"] = f"passo {p['id']} falhou: {r['bloqueio']}"
            break
    rel["medidas"]["passos"] = feitos
    rel["medidas"]["objetivo"] = cartao["objetivo"]
