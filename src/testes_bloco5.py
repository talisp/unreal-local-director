"""v0.0.2 Bloco 5 — testes offline PERMANENTES das correções feitas a partir de dados reais do Unreal (sem Unreal).
1. espera por trava/pausa acaba na próxima tentativa (antes: 10 min fixos escondiam o relógio);
2. emperrado = degrau ativo: tentativa posterior de OUTRA linha não apaga o emperramento de sessão;
3. recusa/macro barrada pela PAUSA é espera, não tentativa;
4. corrida aberta além do prazo declarado vira alarme corrida_perdida (não espera eterna)."""
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import testes_bloco4 as T4  # noqa: E402
from testes_bloco3 import B2, E, M, caso  # noqa: E402
from testes_bloco4_sup import T0, Tempo  # noqa: E402
from unreal_macros import supervisor as S  # noqa: E402


@caso("espera por trava termina na próxima tentativa: 46 min sem progresso alarmam mesmo com espera no meio")
def b5_espera_trava():
    tp = Tempo("b5e1")
    tp.modelo("f", "PC_19", falhos=("deriva_xy",))
    tp.modelo("esp", "PC_19", espera=True)
    tp.em(0, "f")
    tp.em(1, "esp")          # trava ocupada por um instante
    tp.em(2, "f")            # o agente voltou a trabalhar: a espera acabou aqui
    r = tp.sup(48)
    assert {"atividade_sem_progresso", "sem_atividade"} & {a["tipo"] for a in r["alarmes"]} and r["sem_progresso_min"] >= 45, r


@caso("emperrado = degrau ativo: uma tentativa de OUTRA linha depois não apaga o emperramento de sessão")
def b5_degrau_ativo():
    tp = Tempo("b5e2")
    tp.modelo("f", "PC_19", falhos=("deriva_xy",))
    tp.modelo("outra", "PC_20", falhos=("pes_no_chao",))
    tp.em(0, "f")
    tp.em(1, "f")                                          # repetição -> disparo
    rel = dict(tp.modelos["outra"], contexto={"linha": "outra"})  # outra linha, depois
    tp.k += 1
    rel["id"] = f"{T4.D.__name__[:0]}" + __import__("datetime").datetime.fromtimestamp(T0 + 120).strftime("%Y%m%d-%H%M%S") + f"-1-{tp.k}"
    rel["quando_ts"] = T0 + 120
    json.dump(rel, open(os.path.join(tp.L.rel, rel["id"] + ".json"), "w", encoding="utf-8"))
    itens = E.carregar_historico(tp.L.rel, tp.L.exp)
    assert E.avaliar(itens, "L")["emperrado"] and E.avaliar(itens, "L")["degrau"] == "cutucar"


@caso("macro barrada pela PAUSA é espera (tipo pausa), não tentativa")
def b5_pausa_espera():
    L = T4.Linha("b5e3")
    os.makedirs(os.path.join(L.raiz, "supervisor"), exist_ok=True)
    json.dump({"motivo": "teste"}, open(os.path.join(L.raiz, "supervisor", "PAUSA"), "w"))
    orig = M.RAIZ_WORK
    M.RAIZ_WORK = L.raiz
    try:
        rels = [M.medir_personagem("PC_19") for _ in range(3)]
    finally:
        M.RAIZ_WORK = orig
    assert all(r["espera"]["tipo"] == "pausa" for r in rels), [r.get("espera") for r in rels]
    est = E.avaliar(E.carregar_historico(L.rel, L.exp), "medir_personagem")
    assert not est["disparos"] and est["esperas"] == 3, est


@caso("corrida aberta além do prazo declarado -> alarme corrida_perdida, não espera eterna")
def b5_corrida_perdida():
    tp = Tempo("b5e4")
    tp.modelo("ok", "PC_19")
    tp.em(0, "ok")
    tp.evento(1, {"evento": "corrida_iniciada", "experimento": "e1", "n": 1, "script": "src/x.py", "prazo_s": 600})
    dentro = tp.sup(8)
    fora = tp.sup(30)
    assert dentro["esperas_ativas"] and not [a for a in dentro["alarmes"] if a["tipo"] == "corrida_perdida"], dentro
    assert not fora["esperas_ativas"] and [a for a in fora["alarmes"] if a["tipo"] == "corrida_perdida"], fora


if __name__ == "__main__":
    B2._montar_sandbox()
    sys.exit(0 if T4.rodar([b5_espera_trava, b5_degrau_ativo, b5_pausa_espera, b5_corrida_perdida], "bloco5") else 1)
