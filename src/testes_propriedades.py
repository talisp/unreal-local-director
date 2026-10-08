"""Propriedades (Hypothesis) das funções puras de blocos.py: a régua da bateria de quebra (Fase 2a, S4).

Roda com o Python do .venv-ferramentas: `python -m pytest src/testes_propriedades.py`.
- Régua protegida: só o Claude muda este arquivo. O Qwen propõe propriedades novas em work/bateria/propostas/.
- Reproduzível: derandomize=True (semente fixa) e sem banco de exemplos em disco.
- Defeito CONHECIDO (tools/bateria_conhecidos.json, ou o caminho em BATERIA_CONHECIDOS) é pulado aqui e listado
  pela bateria; o que sobrar é defeito NOVO. Cada classe de entrada falha numa linha própria, para o Hypothesis
  relatar cada defeito com o seu exemplo mínimo.
- trava.py não entra: não tem função de estado que não toque o disco ou o sistema.
"""
import json
import math
import os
import sys

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from unreal_macros import blocos as B  # noqa: E402

# Números MEDIDOS no Unreal (06/10), os mesmos de testes_v003_blocos; Open_Door_Outwards só entra no avanço.
INFO = {"Start_Walking": {"avanco_cm": 190.54}, "Walking": {"avanco_cm": 150.16}, "Stop_Walking": {"avanco_cm": 152.27},
        "Sit_To_Stand": {"avanco_cm": 46.64}, "Open_Door_Outwards": {"avanco_cm": 80.0}}
INI, CICLO, FIM = (INFO[c]["avanco_cm"] for c in ("Start_Walking", "Walking", "Stop_Walking"))
VAO_MIN_CM = 150  # régua fixa (V03, 06/10); não lê blocos.PRECONDICOES, para um defeito plantado ali ser pego
DOBRADICA_OK = "esquerda"
ANDAR_MAX_CM = 1e5  # acima de 1 km não é cena: fora do contrato desta propriedade (não testado)

AJUSTE = settings(max_examples=300, derandomize=True, database=None, deadline=None,
                  suppress_health_check=[HealthCheck.too_slow])
# Por classe: a maioria dos exemplos cai em outra classe e é pulada; 1000 exemplos custam < 1 s (funções puras).
AJUSTE_CLASSES = settings(AJUSTE, max_examples=1000)

# ---------- defeitos conhecidos ----------
CONDICOES = {
    "distancia_negativa": lambda a: math.isfinite(a["distancia_cm"]) and a["distancia_cm"] < 0,
    "distancia_zero": lambda a: a["distancia_cm"] == 0,
    "distancia_nao_finita": lambda a: not math.isfinite(a["distancia_cm"]),
    "vao_nao_finito": lambda a: not math.isfinite(a["vao_cm"]),
}


def _conhecidos() -> list:
    caminho = os.environ.get("BATERIA_CONHECIDOS") or os.path.join(AQUI, "..", "tools", "bateria_conhecidos.json")
    if not os.path.exists(caminho):
        return []
    lista = json.load(open(caminho, encoding="utf-8"))
    for e in lista:
        assert e["condicao"] in CONDICOES, f"condição desconhecida em {caminho}: {e['condicao']}"
    return lista


CONHECIDOS = _conhecidos()


def conhecido(contrato: str, args: dict) -> bool:
    return any(e["contrato"] == contrato and CONDICOES[e["condicao"]](args) for e in CONHECIDOS)


def _float(v):
    if isinstance(v, str) and v.strip().lower().lstrip("+-") in ("nan", "inf", "infinity"):
        return float(v)  # JSON não guarda NaN/inf: vêm como "nan", "inf"
    return v


# ---------- contratos ----------
def _recusou(r) -> bool:
    return isinstance(r, dict) and bool(r.get("recusa")) and r.get("passos") == []


def viola_andar(d: float):
    """None se andar(d) cumpre o contrato; senão, o que deu errado."""
    try:
        r = B.andar(d, INFO)
    except Exception as e:  # noqa: BLE001 - exceção no lugar de recusa com motivo é violação
        return f"exceção {type(e).__name__}: {e}"
    if not math.isfinite(d) or d <= 0:
        return None if _recusou(r) else f"aceitou distância inválida ({d}): {r.get('ciclos')} ciclos, {r.get('avanco_cm')} cm"
    if _recusou(r):
        return f"recusou distância válida ({d}): {r['recusa']}"
    if r["avanco_cm"] < 0 or r["ciclos"] < 0:
        return f"avanço ou ciclos negativos: {r}"
    if d >= INI + FIM and abs(r["erro_cm"]) > CICLO / 2 + 0.051:
        return f"erro {r['erro_cm']} cm maior que meio ciclo ({CICLO / 2:.2f})"
    if d < INI + FIM and r["ciclos"] != 0:
        return f"distância menor que começar+parar com {r['ciclos']} ciclos"
    return None


def viola_abrir_porta(vao: float, dobradica: str):
    try:
        r = B.abrir_porta(INFO, vao, dobradica)
    except Exception as e:  # noqa: BLE001
        return f"exceção {type(e).__name__}: {e}"
    deve_recusar = not math.isfinite(vao) or vao < VAO_MIN_CM or dobradica != DOBRADICA_OK
    if deve_recusar and not _recusou(r):
        return f"aceitou vão {vao} cm com dobradiça '{dobradica}'"
    if not deve_recusar and (_recusou(r) or not r.get("passos")):
        return f"recusou vão válido {vao} cm: {r.get('recusa')}"
    return None


# ---------- propriedades ----------
# Uma propriedade por classe de entrada, todas com a MESMA estratégia geral: qualquer float (o Hypothesis tem de gerar
# o NaN, o infinito e o negativo sozinho) ou um valor de tamanho real (vão 0–400 cm, distância −10 a 20 m), porque
# "qualquer float" quase nunca cai perto das fronteiras reais. Separadas porque, ao achar um defeito, ele para de
# procurar outros.
def classe_distancia(d: float) -> str:
    if math.isnan(d):
        return "nan"
    if math.isinf(d):
        return "inf"
    return "negativo" if d < 0 else "zero" if d == 0 else "valido"


def classe_porta(vao: float, dobradica: str) -> str:
    if dobradica != DOBRADICA_OK:  # primeiro: com a dobradiça errada a recusa vem por ela e esconde o vão
        return "dobradica_errada"
    if math.isnan(vao):
        return "nan"
    if math.isinf(vao):
        return "inf"
    return "abaixo_do_minimo" if vao < VAO_MIN_CM else "valido"


@pytest.mark.parametrize("classe", ["nan", "inf", "negativo", "zero", "valido"])
@AJUSTE_CLASSES
@given(d=st.one_of(st.floats(allow_nan=True, allow_infinity=True), st.floats(min_value=-1e3, max_value=2e3)))
def test_andar(classe, d):
    if classe_distancia(d) != classe or (math.isfinite(d) and abs(d) > ANDAR_MAX_CM):
        return
    if conhecido("andar", {"distancia_cm": d}):
        return
    v = viola_andar(d)
    assert v is None, f"andar({d}): {v}"


@pytest.mark.parametrize("classe", ["nan", "inf", "dobradica_errada", "abaixo_do_minimo", "valido"])
@AJUSTE_CLASSES
@given(vao=st.one_of(st.floats(allow_nan=True, allow_infinity=True), st.floats(min_value=0, max_value=400)),
       dobradica=st.sampled_from(["esquerda", "direita", ""]))
def test_abrir_porta(classe, vao, dobradica):
    if classe_porta(vao, dobradica) != classe:
        return
    if conhecido("abrir_porta", {"vao_cm": vao, "dobradica": dobradica}):
        return
    v = viola_abrir_porta(vao, dobradica)
    assert v is None, f"abrir_porta({vao}, '{dobradica}'): {v}"


@AJUSTE
@given(distancias=st.lists(st.floats(min_value=1, max_value=1e4), min_size=1, max_size=4), com_levantar=st.booleans())
def test_compor_e_a_soma_das_partes(distancias, com_levantar):
    partes = ([B.levantar(INFO)] if com_levantar else []) + [B.andar(d, INFO) for d in distancias]
    c = B.compor(*partes)
    assert abs(c["avanco_cm"] - sum(p["avanco_cm"] for p in partes)) <= 0.051, c["avanco_cm"]
    assert c["passos"] == [x for p in partes for x in p["passos"]]
    assert c["partes"] == [p["bloco"] for p in partes]


_coord = st.floats(min_value=-300, max_value=300)


@AJUSTE
@given(quadros=st.lists(st.dictionaries(st.sampled_from(["mao_e", "mao_d", "pe_e", "quadril"]),
                                        st.tuples(_coord, _coord, _coord), max_size=4), max_size=12),
       theta=st.floats(min_value=0, max_value=2 * math.pi), lado=st.sampled_from([1, -1]),
       dobradica=st.tuples(_coord, _coord))
def test_angulos_porta_sem_nan_entre_0_e_100_e_sem_voltar(quadros, theta, lado, dobradica):
    folha = (math.cos(theta), math.sin(theta))
    frente = (-lado * folha[1], lado * folha[0])  # perpendicular à folha
    r = B.angulos_porta(list(enumerate(quadros)), dobradica, frente, folha)
    angulos = [a for _q, a in r["angulos"]]
    assert all(math.isfinite(a) and 0 <= a <= 100 for a in angulos), angulos
    assert all(b >= a for a, b in zip(angulos, angulos[1:])), f"a porta voltou: {angulos}"
    assert r["final_graus"] == (angulos[-1] if angulos else 0.0)


@AJUSTE
@given(graus=st.floats(min_value=0, max_value=100), theta=st.floats(min_value=0, max_value=2 * math.pi),
       lado=st.sampled_from([1, -1]), dobradica=st.tuples(_coord, _coord))
def test_folha_em_sem_nan_e_no_lugar(graus, theta, lado, dobradica):
    folha = (math.cos(theta), math.sin(theta))
    frente = (-lado * folha[1], lado * folha[0])
    (cx, cy), (dx, dy) = B.folha_em(dobradica, folha, frente, graus)
    assert all(math.isfinite(x) for x in (cx, cy, dx, dy))
    assert abs(math.hypot(dx, dy) - 1) < 1e-9
    assert abs(math.hypot(cx - dobradica[0], cy - dobradica[1]) - 50) < 1e-6


# ---------- os conhecidos ainda acontecem? (se não, tire da lista) ----------
@pytest.mark.parametrize("e", CONHECIDOS, ids=[e["id"] for e in CONHECIDOS])
def test_conhecido_ainda_reproduz(e):
    a = {k: _float(v) for k, v in e["entrada_minima"].items()}
    assert CONDICOES[e["condicao"]](a), f"{e['id']}: a entrada mínima não cai na própria condição"
    if e["contrato"] == "andar":
        v = viola_andar(float(a["distancia_cm"]))
    else:
        v = viola_abrir_porta(float(a["vao_cm"]), str(a["dobradica"]))
    assert v is not None, f"{e['id']} não reproduz mais (corrigido?): tire de tools/bateria_conhecidos.json"
