"""Testes da linha 2 (Fase 8), SEM Unreal: a cena, a regra das variações, o executor com a cena, a escolha do operador
e o pedido gerado. O ensaio e a noite (com Unreal) são lançados pelo operador; aqui nada é lançado."""
import importlib.util
import json
import os
import sys
import tempfile

PASTA = tempfile.mkdtemp()
os.environ["FILA_PASTA"] = PASTA  # o executor lê na importação
AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(RAIZ, "tools"))
from testes_v003_bloco1 import caso, rodar  # noqa: E402
from unreal_macros import biblioteca as BIB  # noqa: E402
from unreal_macros import cena as C  # noqa: E402
from unreal_macros import fila as F  # noqa: E402
from unreal_macros import receita as R  # noqa: E402
import fila_executor as X  # noqa: E402  # pyright: ignore[reportMissingImports]


def _mod(nome):
    s = importlib.util.spec_from_file_location(nome, os.path.join(RAIZ, "tools", f"{nome}.py"))
    assert s and s.loader
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


ESC, L2 = _mod("escolha"), _mod("linha2")
CENA = os.path.join(RAIZ, "cenas", "fila.md")
BASE = [{"clipe": "Sit_To_Stand", "papel": "levantar"}, {"clipe": "Victory", "papel": "acenar"},
        {"clipe": "Walking", "papel": "andar"}, {"clipe": "Stop_Walking_2", "papel": "parar"}]


def _receita(acenar="Victory", ponte=None, giro=0, variacao=False):
    passos: list[dict] = [dict(p) for p in BASE]
    passos[1]["clipe"] = acenar
    passos[2]["turn_deg"] = giro
    if ponte:
        passos.insert(2, {"clipe": ponte, "papel": "ponte"})
    r = {"linhagem": "V" if variacao else "A", "tipo": "exploracao", "passos": passos}
    if variacao:
        r["variacao"] = True
    return r


def _tent(n, r, nota=0.0):
    return {"n": n, "tipo_linha": "tentativa", "receita": r["passos"], "assinatura": R.assinatura(r), "nota": nota,
            "variacao": bool(r.get("variacao")), "linhagem": r["linhagem"], "tipo": r["tipo"],
            "avaliacao": {"valida": True, "nota": nota}}


@caso("cena: o modelo da fila vale; papel sem critério, ordem trocada, variações demais e hora errada são recusados")
def t_cena():
    c = C.ler_cena(CENA)
    assert C.validar_cena(c)["ok"] and c["variacoes"] == 3, C.validar_cena(c)
    v = C.validar_cena(dict(c, papeis=["levantar", "sentar"]))
    assert not v["ok"] and v["ausentes"] == ["sentar"] and "critério_ausente" in v["motivos"][0], v
    assert not C.validar_cena(dict(c, papeis=list(reversed(c["papeis"]))))["ok"]
    assert not C.validar_cena(dict(c, variacoes=9))["ok"]
    assert not C.validar_cena(dict(c, ate="8h"))["ok"]


@caso("diferente de verdade: mesma receita, só ponte ou só giro não contam; clipe diferente num papel conta")
def t_diferente():
    base = _receita()
    assert not C.diferente_de_verdade(_receita(), [base])[0]
    assert not C.diferente_de_verdade(_receita(ponte="Idle_16"), [base])[0]
    assert not C.diferente_de_verdade(_receita(giro=10), [base])[0]
    assert C.diferente_de_verdade(_receita(acenar="Waving_2"), [base])[0]


@caso("regra das variações: só depois do sucesso; marcada com 'variacao'; para quando completa")
def t_regra_variacoes():
    t = [_tent(n, _receita()) for n in (1, 2)]
    assert "só depois do sucesso" in C.checar_variacao(_receita(acenar="Waving_2", variacao=True), t, 2)[0]
    t.append(_tent(3, _receita()))  # 3ª nota 0: sucesso
    assert "marque a receita" in C.checar_variacao(_receita(acenar="Waving_2"), t, 2)[0]
    assert C.checar_variacao(_receita(acenar="Waving_2", variacao=True), t, 2) == []
    assert "não conta" in C.checar_variacao(_receita(giro=5, variacao=True), t, 2)[0]
    t += [_tent(4, _receita(acenar="Waving_2", variacao=True)), _tent(5, _receita(acenar="Cheering_2", variacao=True))]
    ev = C.estado_variacoes(t, 2)
    assert ev["fase"] == "completa" and ev["aceitas"] == [4, 5], ev
    assert "já estão prontas" in C.checar_variacao(_receita(acenar="Standing_Greeting", variacao=True), t, 2)[0]


@caso("executor com FILA_CENA: depois do sucesso aceita variação diferente e recusa a repetida")
def t_executor_cena():
    os.environ["FILA_CENA"] = CENA
    hora = X.depois_da_hora
    setattr(X, "depois_da_hora", lambda: False)  # relógio fixo: o caso não testa a hora
    try:
        for f in os.listdir(PASTA):
            os.remove(os.path.join(PASTA, f)) if os.path.isfile(os.path.join(PASTA, f)) else None
        for n in (1, 2, 3):
            X._acrescentar("tentativas.jsonl", _tent(n, _receita()))
        _, m = X.preparar(_receita(acenar="Waving_2", variacao=True))
        assert m == [], m
        _, m = X.preparar(_receita(giro=5, variacao=True))
        assert m and "não conta" in m[0], m
        assert X.estado_resumo()["variacoes"]["fase"] == "variacoes"
    finally:
        setattr(X, "depois_da_hora", hora)
        del os.environ["FILA_CENA"]
    _, m = X.preparar(_receita(acenar="Waving_2", variacao=True))  # sem a cena: a noite de 07/10, sem variações
    assert any("não tem fase de variações" in x for x in m), m


@caso("Astra 08/10 (1): o prazo vale a partir do início da rodada; à tarde do dia seguinte continua fechado")
def t_prazo():
    d = X.dt.datetime
    assert X.prazo_de(d(2026, 10, 8, 20, 0), (7, 30)) == d(2026, 10, 9, 7, 30)  # noite: fecha na manhã seguinte
    assert X.prazo_de(d(2026, 10, 9, 3, 0), (7, 30)) == d(2026, 10, 9, 7, 30)   # madrugada: fecha no mesmo dia
    assert X.prazo_de(d(2026, 10, 9, 8, 0), (7, 30)) == d(2026, 10, 10, 7, 30)  # depois do prazo: o próximo
    # o furo: rodada aberta ontem às 20:00; hoje às 15:00 a regra antiga ('antes do meio-dia') reabria
    e = X._estado()
    e["inicio_rodada"] = (d.now() - X.dt.timedelta(days=1)).replace(hour=20, minute=0).isoformat(timespec="seconds")
    X._gravar_estado(e)
    assert X.depois_da_hora(), "rodada de ontem à noite não pode aceitar tentativa hoje"
    e["inicio_rodada"] = None
    X._gravar_estado(e)


@caso("Astra 08/10 (2): _filho sem a autorização do 'tentar' é recusado e não toca em nada")
def t_filho():
    with tempfile.TemporaryDirectory() as tmp:
        arq = os.path.join(tmp, "r.json")
        json.dump(_receita(), open(arq, "w", encoding="utf-8"))
        antes = X._ler_jsonl("tentativas.jsonl")
        assert X.main(["_filho", arq, "7"]) == 1 and X.main(["_filho", arq, "7", "nonce-falso"]) == 1
        assert X._ler_jsonl("tentativas.jsonl") == antes, "registrou tentativa sem autorização"


@caso("Astra 08/10 (3): o próprio executor recusa cena inválida (papel sem critério), não só o lançador")
def t_cena_invalida_no_executor():
    with tempfile.TemporaryDirectory() as tmp:
        ruim = os.path.join(tmp, "ruim.md")
        open(ruim, "w", encoding="utf-8").write(open(CENA, encoding="utf-8").read().replace(
            "- papeis: levantar, acenar, andar, parar", "- papeis: levantar, sentar"))
        os.environ["FILA_CENA"] = ruim
        try:
            _, m = X.preparar(_receita())
        finally:
            del os.environ["FILA_CENA"]
        assert any("cena inválida" in x and "critério_ausente" in x for x in m), m


@caso("escolha: gera as opções (sucesso + variações) e grava a escolha do operador na biblioteca")
def t_escolha():
    with tempfile.TemporaryDirectory() as tmp:
        rod, bib = os.path.join(tmp, "fila_teste"), os.path.join(tmp, "bib")
        os.makedirs(rod)
        with open(os.path.join(rod, "tentativas.jsonl"), "w", encoding="utf-8") as f:
            for t in [_tent(n, _receita()) for n in (1, 2, 3)] + [_tent(4, _receita(acenar="Waving_2", variacao=True))]:
                f.write(json.dumps(t) + "\n")
        d = ESC.gerar(rod, 3, "fila")
        assert [o["opcao"] for o in d["opcoes"]] == ["base", 4] and d["faltam_variacoes"] == 2, d
        reg = ESC.escolher(rod, "4", bib)
        assert reg["tentativa"] == 4 and BIB.carregar(bib)["escolhas"][reg["id"]]["decisao"] == "Talis"
        assert json.load(open(os.path.join(rod, "escolha.json"), encoding="utf-8"))["escolhida"] == 4
        try:
            ESC.escolher(rod, "9", bib)
            raise AssertionError("aceitou opção inexistente")
        except ValueError:
            pass


@caso("pedido gerado: sem campo sobrando, com comando, critérios da régua e ferramentas de hoje; ensaio só no ensaio")
def t_pedido():
    c = C.ler_cena(CENA)
    p = L2.gerar_pedido(c, "cenas/fila.md", "work/fila_teste", "noite")
    assert not __import__("re").search(r"\{[a-z_]+\}", p), "sobrou campo sem preencher"
    assert 'FILA_PASTA="work/fila_teste" FILA_CENA="cenas/fila.md"' in p and "tools/fila_executor.py" in p
    assert all(f"**{k}:**" in p for k in c["criterios"]) and f"{F.LIM['osso_cm']:g} cm" in p
    assert "corte_fim_q" in p and "consultar_trocas" in p and "ENSAIO" not in p
    assert "## Ensaio" in L2.gerar_pedido(c, "cenas/fila.md", "work/fila_teste", "ensaio")


@caso("antes de lançar: Unreal fechado, modelo fora do ar ou trava ocupada impedem")
def t_ambiente():
    ok = "  TCP    127.0.0.1:8001   0.0.0.0:0   LISTENING   1\n  TCP    127.0.0.1:8080   0.0.0.0:0   LISTENING   2\n"
    assert L2.checar_ambiente(ok, False) == []
    assert any("8001" in m for m in L2.checar_ambiente(ok.split("\n")[1], False))
    assert any("trava" in m for m in L2.checar_ambiente(ok, True))


if __name__ == "__main__":
    sys.exit(0 if rodar([t_cena, t_diferente, t_regra_variacoes, t_executor_cena, t_prazo, t_filho,
                         t_cena_invalida_no_executor, t_escolha, t_pedido, t_ambiente], "cena") else 1)
