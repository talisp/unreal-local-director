"""Testes do tools/director.py (o painel das 4 linhas), SEM rodar nenhuma linha de verdade."""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from testes_v003_bloco1 import caso, rodar  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("director", os.path.join(RAIZ, "tools", "director.py"))
assert _spec and _spec.loader
D = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(D)


@caso("estado: uma linha para cada uma das 4 linhas de trabalho, sem rodar nada")
def t_estado():
    e = D.estado()
    assert [x[0] for x in e] == ["bateria", "junior", "unreal", "astra"] and all(x[1] for x in e), e


@caso("unreal sem modo nunca lança: vira --seco com a cena padrão; os outros repassam os argumentos")
def t_rodar():
    chamadas = []

    class Falso:
        returncode = 0

    sub = D.subprocess.run
    setattr(D.subprocess, "run", lambda cmd, **k: chamadas.append(cmd) or Falso())
    try:
        assert D.rodar("unreal", []) == 0 and D.rodar("junior", ["--tema", "3", "--seco"]) == 0
    finally:
        setattr(D.subprocess, "run", sub)
    assert chamadas[0][1].endswith("linha2.py") and "--seco" in chamadas[0] and "--cena" in chamadas[0], chamadas[0]
    assert "--ensaio" not in chamadas[0] and "--noite" not in chamadas[0]
    assert chamadas[1][-3:] == ["--tema", "3", "--seco"] and chamadas[1][1].endswith("junior.py"), chamadas[1]


if __name__ == "__main__":
    sys.exit(0 if rodar([t_estado, t_rodar], "director") else 1)
