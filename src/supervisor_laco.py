"""Executor periódico MÍNIMO do supervisor (v0.0.2, bloco 5) — sucessor do vigia_travas, sem inteligência nova.

Uso:  python supervisor_laco.py [--intervalo 600] [--vezes 0] [--hashes ARQ --base DIR] [--sandbox DIR --guarda-sha SHA]
      (--vezes 0 = até ser parado; para parar: Ctrl+C ou criar work/supervisor/PARAR_LACO)

O que faz: chama supervisor.avaliar() a cada intervalo e registra cada execução em work/supervisor/laco.log.
O que NÃO faz: não chama o Unreal, não remove PAUSA, não conserta nada, não decide correções. Se a própria avaliação
falhar, registra o erro e continua (3 falhas seguidas = para, conservador: um supervisor quebrado não fica fingindo
que está vigiando).
"""
import argparse
import datetime as dt
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unreal_macros import supervisor as S  # noqa: E402
from unreal_macros.macros import RAIZ_WORK, pausa_ativa  # noqa: E402

PASTA = os.path.join(RAIZ_WORK, "supervisor")


def _log(linha: dict, pasta: str):
    os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, "laco.log"), "a", encoding="utf-8") as f:
        f.write(json.dumps(dict(linha, quando=dt.datetime.now().isoformat(timespec="seconds")), ensure_ascii=False, default=str) + "\n")


def uma_vez(agora: float = None, pasta: str = PASTA, **kw) -> dict:
    """Uma execução: avalia e registra. Devolve o resumo gravado."""
    r = S.avaliar(agora or time.time(), pasta_sup=pasta, **kw)
    resumo = {"evento": "avaliacao", "alarmes": [a["tipo"] for a in r["alarmes"]], "sem_progresso_min": r["sem_progresso_min"],
              "esperas": [e["tipo"] for e in r["esperas_ativas"]], "pausa": bool(r["pausa"] or pausa_ativa()),
              "ultimo_progresso": r["ultimo_progresso"]}
    _log(resumo, pasta)
    return resumo


def laco(intervalo: float, vezes: int = 0, pasta: str = PASTA, relogio=time.time, dormir=time.sleep, **kw) -> int:
    _log({"evento": "inicio", "intervalo_s": intervalo, "vezes": vezes}, pasta)
    falhas, n = 0, 0
    while True:
        if os.path.exists(os.path.join(pasta, "PARAR_LACO")):
            _log({"evento": "parado", "motivo": "arquivo PARAR_LACO"}, pasta)
            return 0
        try:
            uma_vez(relogio(), pasta, **kw)
            falhas = 0
        except Exception as e:  # noqa: BLE001
            falhas += 1
            _log({"evento": "erro", "erro": f"{type(e).__name__}: {e}", "falhas_seguidas": falhas}, pasta)
            if falhas >= 3:
                _log({"evento": "parado", "motivo": "3 falhas seguidas do próprio supervisor"}, pasta)
                return 2
        n += 1
        if vezes and n >= vezes:
            _log({"evento": "fim", "execucoes": n}, pasta)
            return 0
        dormir(intervalo)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--intervalo", type=float, default=600)
    ap.add_argument("--vezes", type=int, default=0)
    ap.add_argument("--hashes")
    ap.add_argument("--base")
    ap.add_argument("--sandbox")
    ap.add_argument("--guarda-sha")
    a = ap.parse_args()
    try:
        sys.exit(laco(a.intervalo, a.vezes, hashes_producao=a.hashes, base_producao=a.base, sandbox=a.sandbox,
                      guarda_sha_base=a.guarda_sha))
    except KeyboardInterrupt:
        _log({"evento": "parado", "motivo": "Ctrl+C"}, PASTA)
