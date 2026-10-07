"""v0.0.2 Bloco 4 — direção (banco/capacidades/fila), supervisor, passagem de sessão e rotação. SEM Unreal.
Registros nos formatos REAIS: envelope real das macros (testes_bloco3.Linha) e controlador real (sandbox git falso)."""
import json
import os
import shutil
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import testes_bloco3 as T3  # noqa: E402
from testes_bloco3 import B2, E, X, Linha, M, caso, resultados  # noqa: E402
from unreal_macros import direcao as D  # noqa: E402

TMP = T3.TMP


# ---------- caracterização do que o bloco 4 consome ----------
@caso("caracterização: relatório traz a versão do código (lacuna corrigida na origem)")
def c_versao():
    L = Linha("b4-car")
    rel = L.macro("PC_19")
    v = rel["ambiente"].get("versao_codigo")
    assert v and len(v) == 12 and v == M.versao_codigo(), rel["ambiente"]


# ---------- seção 1: banco de pedidos + capacidades ----------
@caso("banco e mapa válidos: pedidos só apontam para capacidades do mapa; disponível cita ferramenta real")
def b_valido():
    assert D.validar() == [], D.validar()
    v0 = [p for p in D.pedidos() if p.get("familia") != "vertical"]
    vert = sorted(p["id"] for p in D.pedidos() if p.get("familia") == "vertical")  # v0.0.3 bloco 2: escada do chá
    assert 18 <= len(v0) <= 22 and {p["nivel"] for p in D.pedidos()} == {1, 2}
    assert vert == [f"V0{i}" for i in range(1, 8)], vert


@caso("capacidade inexistente continua inexistente (as futuras estão marcadas) e não cita ferramenta")
def b_inexistentes():
    caps = D.capacidades()
    for c in ("ir_ate_ponto", "porta", "escada", "sentar", "construir_lugar"):
        assert caps[c]["estado"] == "inexistente" and not caps[c]["ferramentas"], c
    assert D.atendibilidade("P09")["situacao"] == "nao_atendivel" and D.atendibilidade("P09")["faltam"] == ["sentar"]
    assert D.atendibilidade("P01")["situacao"] == "atendivel"


@caso("validação pega capacidade inventada: 'disponível' citando ferramenta que não existe é erro")
def b_inventada():
    orig = D.capacidades
    D.capacidades = lambda: dict(orig(), porta={"estado": "disponivel", "ferramentas": ["abrir_porta"]})
    try:
        erros = D.validar()
    finally:
        D.capacidades = orig
    assert any("abrir_porta" in e for e in erros), erros


@caso("experimento aceita pedido real ou 'infraestrutura/transversal'; pedido inventado é recusado")
def b_pedido_exp():
    L = Linha("b4-ped")
    e = X.iniciar("ped-real", "experimento", "ajuda o pedido P08 (ir até a porta)", hipoteses=[B2.H_A, B2.H_B],
                  sandbox=B2.SB, pasta=L.exp, pedido="P08")
    t = X.iniciar("ped-transv", "experimento", "infraestrutura de captura", hipoteses=[B2.H_A, B2.H_B],
                  sandbox=B2.SB, pasta=L.exp, pedido=D.TRANSVERSAL)
    assert e["pedido"] == "P08" and t["pedido"] == D.TRANSVERSAL
    T3_recusa(X.iniciar, "ped-falso", "experimento", "pedido que não existe", hipoteses=[B2.H_A, B2.H_B],
              sandbox=B2.SB, pasta=L.exp, pedido="P99", contem="não existe no banco")


def T3_recusa(fn, *a, contem="", **k):
    try:
        fn(*a, **k)
    except X.Recusa as e:
        assert contem.lower() in str(e).lower(), str(e)
        return
    raise AssertionError("deveria ter recusado")


# ---------- seção 2: fila por valor ----------
def _conhecidos(L):
    return D.resultados_conhecidos(L.rel, os.path.join(L.raiz, "relatorios_arquivo", "indice.jsonl"))


@caso("exploração exclui caso já respondido nesta versão do código; caso novo entra como informação nova")
def f_exploracao():
    L = Linha("b4-fila")
    L.macro("PC_19", falhos=("deriva_xy",))
    casos = [{"id": "E1", "tipo": "exploracao", "macro": "_fx", "args": ["PC_19"], "kwargs": {"falhos": ["deriva_xy"]}},
             {"id": "E2", "tipo": "exploracao", "macro": "_fx", "args": ["PC_20"], "kwargs": {}}]
    r = D.montar_fila(casos, M.versao_codigo(), _conhecidos(L))
    assert [c["id"] for c in r["excluidos"]] == ["E1"] and [(c["id"], c["motivo"]) for c in r["fila"]] == [("E2", "informacao_nova")], r


@caso("regressão mantém caso conhecido: em dia nesta versão; volta à fila se o código mudou; nunca é removido")
def f_regressao():
    L = Linha("b4-regr")
    L.macro("PC_19")
    caso_c = {"id": "C1", "tipo": "contrato", "macro": "_fx", "args": ["PC_19"], "kwargs": {}}
    r = D.montar_fila([caso_c], M.versao_codigo(), _conhecidos(L))
    assert r["fila"] == [] and [c["id"] for c in r["contrato_em_dia"]] == ["C1"], r
    r2 = D.montar_fila([caso_c], "versaonova99", _conhecidos(L))
    assert [(c["id"], c["motivo"]) for c in r2["fila"]] == [("C1", "regressao")], r2


@caso("repetir caso conhecido só com justificativa verificável (confirmação/desempate com referência real)")
def f_justificativa():
    L = Linha("b4-just")
    L.macro("PC_19", falhos=("deriva_xy",))
    c = {"id": "E1", "tipo": "exploracao", "macro": "_fx", "args": ["PC_19"], "kwargs": {"falhos": ["deriva_xy"]}}
    valida = lambda ref: ref == "exp2-deriva"  # noqa: E731
    boa = D.montar_fila([c], M.versao_codigo(), _conhecidos(L), {"E1": {"motivo": "confirmacao_correcao", "referencia": "exp2-deriva"}}, valida)
    ruim = D.montar_fila([c], M.versao_codigo(), _conhecidos(L), {"E1": {"motivo": "confirmacao_correcao", "referencia": "inventada"}}, valida)
    vaga = D.montar_fila([c], M.versao_codigo(), _conhecidos(L), {"E1": {"motivo": "porque sim", "referencia": "exp2-deriva"}}, valida)
    assert boa["fila"][0]["motivo"] == "confirmacao_correcao" and not ruim["fila"] and not vaga["fila"]
    assert "justificativa recusada" in ruim["excluidos"][0]["motivo_exclusao"]


SECAO_DIRECAO = [c_versao, b_valido, b_inexistentes, b_inventada, b_pedido_exp, f_exploracao, f_regressao, f_justificativa]


def rodar(lista, rotulo):
    for fn in lista:
        fn()
    for nome, ok, msg in resultados:
        print(("OK   " if ok else "FALHA") + " " + nome + (f" | {msg}" if msg else ""))
    print(f"{rotulo}: {sum(ok for _, ok, _ in resultados)}/{len(resultados)}")


if __name__ == "__main__":
    B2._montar_sandbox()
    secoes = SECAO_DIRECAO + globals().get("SECAO_SUPERVISOR", []) + globals().get("SECAO_SESSAO", []) + \
        globals().get("SECAO_ROTACAO", []) + globals().get("SECAO_INTEGRACAO", [])
    rodar(secoes, "bloco4")
