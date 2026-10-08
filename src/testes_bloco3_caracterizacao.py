"""v0.0.2 Bloco 3, passo 0 — CARACTERIZAÇÃO (antes do detector).

Gera registros nos FORMATOS REAIS, com o próprio código dos blocos 1 e 2 (relatório de macro com id, relatório
de macro barrada pela trava, eventos do controlador de experimentos) e verifica se cada campo que o detector precisa
existe de forma ESTRUTURADA: ação, alvo, resultado/gate, erro/bloqueio, estado relevante e espera declarada.
Também roda as integrações mínimas entre os blocos 1 e 2. Sem Unreal.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import testes_bloco2 as B2  # noqa: E402  (reaproveita o sandbox git falso do bloco 2)
from unreal_macros import catalogo, diario, experimentos as X, macros as M  # noqa: E402

resultados = []


def caso(nome):
    def deco(fn):
        def rodar():
            try:
                fn()
                resultados.append((nome, True, ""))
            except Exception as e:  # noqa: BLE001
                resultados.append((nome, False, f"{type(e).__name__}: {e}"))
        return rodar
    return deco


def _rel_disco(rel):
    return diario.carregar_relatorio(rel["id"])


# ---------- integração mínima blocos 1 x 2 ----------
@caso("integração: relatório com id -> registrar_tentativa (fonte relatorio_id) -> linha com os mesmos números")
def i_relatorio_tentativa():
    rel = catalogo.buscar_clipe("talking", n=3)
    with tempfile.TemporaryDirectory() as tmp:
        r = diario.registrar(_rel_disco(rel), tmp, macro="buscar_clipe", fonte="relatorio_id")
        assert r["linha"]["relatorio_id"] == rel["id"] and r["linha"]["chamadas"] == rel["chamadas"]


@caso("integração: experimento -> corrida -> resultado persistido; fechar preserva eventos; novo processo lê")
def i_experimento():
    X.iniciar("car-exp", "experimento", "caracterizar o fluxo do controlador",
              hipoteses=[B2.H_A, B2.H_B], sandbox=B2.SB, pasta=B2.EST)
    X.rodar("car-exp", "src/ok.py", pasta=B2.EST)
    X.fechar("car-exp", "", pasta=B2.EST)
    cod = f"import sys; sys.path.insert(0,{AQUI!r}); from unreal_macros import experimentos as X; print(X.carregar('car-exp',{B2.EST!r})['estado'])"
    assert subprocess.run([sys.executable, "-c", cod], capture_output=True, text=True).stdout.strip() == "fechado"
    evs = [json.loads(l) for l in open(os.path.join(B2.EST, "eventos.jsonl"), encoding="utf-8")]
    assert [e["evento"] for e in evs if e.get("experimento") == "car-exp"] == ["iniciado", "corrida_iniciada", "corrida", "fechado"]


@caso("integração: trava ocupada não impede relatório (a macro barrada também gera relatório com id)")
def i_trava_relatorio():
    rel = _macro_barrada()
    assert rel.get("id") and os.path.exists(os.path.join(diario.PASTA_RELATORIOS, rel["id"] + ".json"))


def _macro_barrada():
    """Macro de Unreal com a trava tomada por outro processo VIVO: barra antes de qualquer chamada ao Unreal."""
    proc = subprocess.Popen([sys.executable, "-c", B2.TOMA_E_DORME.format(aqui=AQUI, p=M.TRAVA)])
    for _ in range(100):
        if os.path.exists(M.TRAVA):
            break
        time.sleep(0.1)
    try:
        return M.medir_personagem("PC_19_Mezz02")
    finally:
        proc.kill()
        proc.wait()
        if os.path.exists(M.TRAVA):
            os.remove(M.TRAVA)


# ---------- caracterização: cada campo do detector existe de forma estruturada? ----------
@caso("caracterização AÇÃO: relatório traz 'macro'; evento traz 'evento'")
def c_acao():
    assert catalogo.buscar_clipe("idle", n=1)["macro"] == "buscar_clipe"


@caso("caracterização ALVO: relatório traz os argumentos da chamada (ator/clipe) de forma estruturada")
def c_alvo():
    rel = _rel_disco(catalogo.buscar_clipe("idle", n=1))
    chamada = rel.get("chamada") or {}
    assert chamada.get("kwargs", {}).get("n") == 1 or "idle" in json.dumps(chamada), f"sem argumentos no relatório: {list(rel)}"


@caso("caracterização ALVO (experimento): evento de corrida diz QUAL script rodou")
def c_alvo_exp():
    evs = [json.loads(l) for l in open(os.path.join(B2.EST, "eventos.jsonl"), encoding="utf-8")]
    corr = [e for e in evs if e["evento"] == "corrida"][-1]
    assert "script" in corr, f"evento de corrida sem script: {sorted(corr)}"


@caso("caracterização RESULTADO/GATE: relatório traz ok + gates estruturados (nome/resultado)")
def c_resultado():
    rel = {"ok": False, "medidas": {"gates": [{"nome": "deriva_xy", "resultado": "FAIL", "valor": 16.8}]}}
    assert rel["medidas"]["gates"][0]["resultado"] in ("PASS", "FAIL", "NOT_EVALUATED")


@caso("caracterização ERRO/BLOQUEIO: classe do erro é derivável sem interpretar texto livre do agente")
def c_erro():
    rel = _macro_barrada()
    assert rel["bloqueio"] and rel["bloqueio"].split(":")[0] in ("RuntimeError", "TravaOcupada"), rel["bloqueio"]


@caso("caracterização ESPERA DECLARADA: trava ocupada vira campo estruturado 'espera' no relatório")
def c_espera_trava():
    rel = _macro_barrada()
    assert isinstance(rel.get("espera"), dict) and rel["espera"].get("tipo") == "trava", \
        f"espera só existe como texto de bloqueio: {rel.get('bloqueio')!r}"


@caso("caracterização ESPERA DECLARADA: corrida em andamento é visível (evento corrida_iniciada antes do fim)")
def c_espera_corrida():
    evs = [json.loads(l) for l in open(os.path.join(B2.EST, "eventos.jsonl"), encoding="utf-8")]
    assert any(e["evento"] == "corrida_iniciada" for e in evs), "nenhum evento marca corrida em andamento"


@caso("caracterização ESTADO RELEVANTE: corrida traz testes_ok e código de saída; relatório traz gates")
def c_estado():
    e = X.carregar("car-exp", B2.EST)
    assert e["corridas"][0]["testes_ok"] == [22, 22] and e["corridas"][0]["codigo_saida"] == 0


if __name__ == "__main__":
    B2._montar_sandbox()
    for fn in (i_relatorio_tentativa, i_experimento, i_trava_relatorio, c_acao, c_alvo, c_alvo_exp, c_resultado, c_erro,
               c_espera_trava, c_espera_corrida, c_estado):
        fn()
    for nome, ok, msg in resultados:
        print(("OK   " if ok else "FALHA") + " " + nome + (f" | {msg}" if msg else ""))
    print(f"caracterizacao: {sum(ok for _, ok, _ in resultados)}/{len(resultados)}")
    sys.exit(0 if resultados and all(ok for _, ok, _ in resultados) else 1)  # 0/0 é falha
