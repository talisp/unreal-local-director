"""Testes do tools/astra.py (linha 3), SEM chamar o Codex: pacote por script, pedido, conferência da resposta e a
trava de cota (--enviar sem --confirmo-cota não chama nada)."""
import importlib.util
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from testes_v003_bloco1 import caso, rodar  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("astra", os.path.join(RAIZ, "tools", "astra.py"))
assert _spec and _spec.loader
A = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A)

BOA = """Olhei a régua e o executor.
```json
{"pergunta": "A régua tem furo?", "achados": [{"achado": "andar(0) era aceito", "gravidade": "media",
 "prova": "src/unreal_macros/blocos.py:24", "correcao": "recusar zero", "verificado": true}], "resumo": "1 achado"}
```"""


@caso("pacote: sai de script, igual em duas chamadas, com a pergunta, o commit e as seções; recusa pergunta vazia")
def t_pacote():
    p1 = A.montar_pacote("O pedido da Fase 8 tem furo?", ["docs/PLANO_PROXIMA_VERSAO.md"], resumo_bateria='{"ok": true}')
    p2 = A.montar_pacote("O pedido da Fase 8 tem furo?", ["docs/PLANO_PROXIMA_VERSAO.md"], resumo_bateria='{"ok": true}')
    assert p1 == p2 and len(p1) <= A.PACOTE_MAX + 60
    for s in ("## A pergunta", "## Commit-base", "## Arquivos que você pode abrir", "## Mudança desde a última revisão",
              "## Bateria neste commit", "## Números que valem", "## Pendências abertas"):
        assert s in p1, s
    for ruim in (("", []), ("pergunta", ["nao/existe.md"])):
        try:
            A.montar_pacote(*ruim)
            raise AssertionError(f"aceitou {ruim}")
        except ValueError:
            pass


@caso("pedido: as regras da rotina (só leitura, prova arquivo:linha, bloco JSON) vão junto com o pacote")
def t_pedido():
    ped = A.montar_pedido("PACOTE-X")
    assert "Não edite nada" in ped and "```json" in ped and ped.rstrip().endswith("PACOTE-X"), ped[-200:]


@caso("resposta: a boa passa; sem JSON, gravidade errada, prova inexistente ou 'verificado' não booleano reprovam")
def t_resposta():
    assert A.conferir_resposta(BOA)["ok"], A.conferir_resposta(BOA)
    casos = {"sem bloco": "texto sem json", "gravidade": BOA.replace('"media"', '"enorme"'),
             "arquivo inexistente": BOA.replace("blocos.py:24", "nao_existe.py:3"),
             "linha inexistente": BOA.replace("blocos.py:24", "blocos.py:99999"),
             "true ou false": BOA.replace('"verificado": true', '"verificado": "sim"')}
    for motivo, texto in casos.items():
        r = A.conferir_resposta(texto)
        assert not r["ok"] and any(motivo in m for m in r["motivos"]), (motivo, r["motivos"])
    vazio = A.conferir_resposta('```json\n{"pergunta": "x", "achados": [], "resumo": "nada"}\n```')
    assert vazio["ok"] and vazio["achados"] == []


@caso("escalada gravada com o commit revisado; a próxima revisão parte dele")
def t_escalada():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "escaladas"))
        raiz = A.RAIZ
        try:
            setattr(A, "RAIZ", tmp)
            assert A.ultima_revisao() is None
            rel = A.gravar_escalada("teste", "A régua tem furo?", "abc1234def56", BOA, A.conferir_resposta(BOA, raiz), "2026-10-09")
            texto = open(os.path.join(tmp, rel), encoding="utf-8").read()
            assert rel == "escaladas/2026-10-09-ASTRA-teste.md" and "| 1 | media |" in texto, texto[:300]
            assert A.ultima_revisao() == "abc1234def56"
        finally:
            setattr(A, "RAIZ", raiz)


@caso("trava de cota: --enviar sem --confirmo-cota sai com 2 e não chama o Codex")
def t_trava_cota():
    chamou = []
    enviar = A.enviar
    setattr(A, "enviar", lambda *a, **k: chamou.append(a) or 0)
    try:
        codigo = A.main(["--tema", "teste-unidade", "--pergunta", "x?", "--enviar"])
    finally:
        setattr(A, "enviar", enviar)
        shutil.rmtree(os.path.join(RAIZ, "work", "astra", f"{A.dt.date.today().isoformat()}-teste-unidade"), ignore_errors=True)
    assert codigo == 2 and chamou == [], (codigo, chamou)


if __name__ == "__main__":
    sys.exit(0 if rodar([t_pacote, t_pedido, t_resposta, t_escalada, t_trava_cota], "astra") else 1)
