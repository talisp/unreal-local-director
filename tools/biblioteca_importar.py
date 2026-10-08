"""Importa uma rodada da fila (tentativas.jsonl + encaixes.jsonl) para a biblioteca (biblioteca/*.jsonl, no git).

Uso: venv\\Scripts\\python.exe tools\\biblioteca_importar.py work\\fila_2026-10-07 fila_2026-10-07
Importar de novo a mesma rodada não duplica (o id substitui). Sem Unreal.
"""
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
from unreal_macros import biblioteca as BIB  # noqa: E402  # pyright: ignore[reportMissingImports]


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    pasta, fonte = os.path.abspath(argv[0]), argv[1]
    r = BIB.importar_rodada(pasta, fonte)
    total = BIB.mesclar(BIB.PASTA, r)
    print(json.dumps({"importados": {t: len(r[t]) for t in BIB.TIPOS}, "linhas_cortadas": r["cortadas"],
                      "na_biblioteca": total}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
