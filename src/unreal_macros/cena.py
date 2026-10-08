"""Cena da linha 2 (Fase 8): o que o operador pede, lido de `cenas/<nome>.md`, e a fase de variações. Puro (sem Unreal).

A régua (fila.py) NÃO muda aqui: a cena só pode pedir critérios do catálogo que a régua de hoje mede. Papel sem
critério vira `critério_ausente` (a cena não roda; o item vai para as pendências do Claude).
Variação "diferente de verdade" (decisão 0.9 do plano): assinatura diferente E clipe diferente em pelo menos um papel,
em relação à receita de sucesso e a toda variação já aceita.
"""
import re

from . import fila as F
from . import receita as R

CATALOGO = tuple(F.PAPEIS) + ("trocas", "duracao")
CAMPOS = ("nome", "descricao", "papeis", "pode_variar", "fixo", "criterios", "variacoes", "prazo_tentativas", "ate")
VARIACOES_MAX = 5


def ler_cena(caminho: str) -> dict:
    c = {}
    for linha in open(caminho, encoding="utf-8"):
        m = re.match(r"^\s*-\s*([a-z_]+)\s*:\s*(.*?)\s*$", linha)
        if m and m.group(1) in CAMPOS:
            c[m.group(1)] = m.group(2)
    lista = lambda s: [x.strip() for x in str(s or "").split(",") if x.strip()]  # noqa: E731
    c["papeis"], c["criterios"] = lista(c.get("papeis")), lista(c.get("criterios"))
    try:
        c["variacoes"] = int(c.get("variacoes", 0))
    except ValueError:
        c["variacoes"] = -1
    return c


def validar_cena(c: dict) -> dict:
    """{ok, ausentes, motivos}. ausentes = papéis/critérios que a régua de hoje não mede (critério_ausente)."""
    motivos, ausentes = [], []
    if not c.get("nome") or not re.fullmatch(r"[a-z0-9_-]+", c["nome"]):
        motivos.append("nome: só letras minúsculas, números, _ e -")
    for p in c.get("papeis", []):
        if p not in F.PAPEIS:
            ausentes.append(p)
    for k in c.get("criterios", []):
        if k not in CATALOGO:
            ausentes.append(k)
    if ausentes:
        motivos.append(f"critério_ausente: a régua de hoje não mede {sorted(set(ausentes))} (catálogo: {list(CATALOGO)})")
    elif c.get("papeis") != list(F.PAPEIS):
        motivos.append(f"a régua de hoje mede os papéis nesta ordem e todos juntos: {list(F.PAPEIS)}")
    if not 0 <= c.get("variacoes", -1) <= VARIACOES_MAX:
        motivos.append(f"variacoes: número de 0 a {VARIACOES_MAX}")
    for k in ("prazo_tentativas", "ate"):
        if not re.fullmatch(r"\d{2}:\d{2}", str(c.get(k, ""))):
            motivos.append(f"{k}: hora no formato HH:MM")
    return {"ok": not motivos, "ausentes": sorted(set(ausentes)), "motivos": motivos}


# ---------- variações ----------
def clipes_por_papel(receita: dict) -> dict:
    out = {}
    for p in receita.get("passos", []):
        out.setdefault(p.get("papel"), []).append(p.get("clipe"))
    return out


def diferente_de_verdade(receita: dict, referencias: list) -> tuple:
    """(sim/não, motivo) em relação a cada receita de referência (a de sucesso e as variações já aceitas)."""
    a = R.assinatura(receita)
    meus = clipes_por_papel(receita)
    for ref in referencias:
        if R.assinatura(ref) == a:
            return False, "é a mesma receita (mesma assinatura) de uma já aceita"
        dele = clipes_por_papel(ref)
        if not any(meus.get(p) != dele.get(p) for p in set(meus) | set(dele) if p != "ponte"):
            return False, "nenhum papel mudou de clipe em relação a uma receita já aceita (mudar só ponte ou giro não conta)"
    return True, "diferente"


def estado_variacoes(tentativas: list, k: int) -> dict:
    """Base = a receita do sucesso (3 notas 0); aceitas = tentativas marcadas `variacao` com nota 0 e diferentes de
    verdade da base e das anteriores, na ordem em que passaram."""
    suc = F.sucesso(tentativas)
    if not suc:
        return {"fase": "sucesso_pendente", "base": None, "aceitas": [], "faltam": k}
    base = next(t for t in tentativas if t.get("assinatura") == suc["assinatura"] and t.get("nota") == 0)
    refs, aceitas = [{"passos": base["receita"]}], []
    for t in tentativas:
        if t.get("variacao") and t.get("nota") == 0:
            r = {"passos": t["receita"]}
            if diferente_de_verdade(r, refs)[0]:
                refs.append(r)
                aceitas.append(t["n"])
    faltam = max(0, k - len(aceitas))
    return {"fase": "variacoes" if faltam else "completa", "base": base["n"], "assinatura_base": suc["assinatura"],
            "aceitas": aceitas, "faltam": faltam, "referencias": refs}


def checar_variacao(receita: dict, tentativas: list, k: int) -> list:
    """Motivos de recusa (vazio = pode) para a regra das variações."""
    ev = estado_variacoes(tentativas, k)
    if receita.get("variacao"):
        if k <= 0:
            return ["esta cena não pede variações"]
        if ev["fase"] == "sucesso_pendente":
            return ["variações só depois do sucesso (a mesma receita com nota 0 três vezes)"]
        if ev["fase"] == "completa":
            return [f"as {k} variações já estão prontas: escreva o FECHAMENTO"]
        ok, motivo = diferente_de_verdade(receita, ev["referencias"])
        return [] if ok else [f"variação recusada: {motivo}"]
    if ev["fase"] == "variacoes":
        return [f"fase de variações: marque a receita com \"variacao\": true (faltam {ev['faltam']} de {k})"]
    return []
