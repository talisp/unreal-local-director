"""A escolha do operador (linha 2, Fase 8): qual das receitas da cena (a de sucesso e as variações) vale.

Uso (na raiz):
  venv\\Scripts\\python.exe tools\\escolha.py gerar work\\<rodada> [--cena cenas\\fila.md]
      grava work/<rodada>/escolha.json: a receita de sucesso e as variações, com nota e vídeo
  venv\\Scripts\\python.exe tools\\escolha.py escolher work\\<rodada> <N | base>
      registra a escolha do operador na biblioteca (biblioteca/escolhas.jsonl) e no escolha.json
Sem Unreal.
"""
import datetime as dt
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
from unreal_macros import biblioteca as BIB  # noqa: E402  # pyright: ignore[reportMissingImports]
from unreal_macros import cena as C  # noqa: E402  # pyright: ignore[reportMissingImports]
from unreal_macros import receita as R  # noqa: E402  # pyright: ignore[reportMissingImports]


def _tentativas(pasta: str) -> list:
    regs, _ = BIB.ler_jsonl(os.path.join(pasta, "tentativas.jsonl"))
    return [t for t in regs if t.get("tipo_linha") == "tentativa" and (t.get("avaliacao") or {}).get("valida")]


def _video(pasta: str, n: int) -> str | None:
    v = os.path.join(pasta, "videos", f"t{n:03d}.mp4")
    return os.path.relpath(v, RAIZ).replace("\\", "/") if os.path.exists(v) else None


def gerar(pasta: str, k: int | None = None, nome_cena: str | None = None) -> dict:
    tent = _tentativas(pasta)
    k = k if k is not None else sum(1 for t in tent if t.get("variacao"))
    ev = C.estado_variacoes(tent, k)
    if ev["base"] is None:
        raise ValueError("ainda não há sucesso (a mesma receita com nota 0 três vezes): nada para escolher")
    por_n = {t["n"]: t for t in tent}
    opcoes = [{"opcao": "base", "n": ev["base"], "receita": por_n[ev["base"]]["receita"],
               "nota": por_n[ev["base"]]["nota"], "video": _video(pasta, ev["base"])}]
    opcoes += [{"opcao": n, "n": n, "receita": por_n[n]["receita"], "nota": por_n[n]["nota"], "video": _video(pasta, n)}
               for n in ev["aceitas"]]
    d = {"rodada": os.path.basename(os.path.normpath(pasta)), "cena": nome_cena, "opcoes": opcoes, "escolhida": None,
         "faltam_variacoes": ev["faltam"],
         "como_escolher": f"venv\\Scripts\\python.exe tools\\escolha.py escolher {os.path.relpath(pasta, RAIZ)} <base|N>"}
    json.dump(d, open(os.path.join(pasta, "escolha.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return d


def escolher(pasta: str, escolha: str, pasta_bib: str = BIB.PASTA) -> dict:
    arq = os.path.join(pasta, "escolha.json")
    if not os.path.exists(arq):
        raise ValueError("escolha.json não existe: rode 'gerar' antes")
    d = json.load(open(arq, encoding="utf-8"))
    alvo = next((o for o in d["opcoes"] if str(o["opcao"]) == str(escolha)), None)
    if alvo is None:
        raise ValueError(f"opção {escolha!r} não está em escolha.json (opções: {[o['opcao'] for o in d['opcoes']]})")
    reg = {"id": f"{d['rodada']}:{alvo['opcao']}", "fonte": d["rodada"], "cena": d.get("cena"), "opcao": alvo["opcao"],
           "tentativa": alvo["n"], "receita": alvo["receita"], "assinatura": R.assinatura({"passos": alvo["receita"]}),
           "video": alvo["video"], "decisao": "Talis", "quando": dt.datetime.now().isoformat(timespec="seconds")}
    BIB.mesclar(pasta_bib, {"escolhas": [reg]})
    d["escolhida"] = alvo["opcao"]
    json.dump(d, open(arq, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return reg


def main(argv) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    if len(argv) < 2 or argv[0] not in ("gerar", "escolher"):
        print(__doc__)
        return 2
    pasta = os.path.abspath(argv[1])
    try:
        if argv[0] == "gerar":
            cena = C.ler_cena(argv[argv.index("--cena") + 1]) if "--cena" in argv else None
            d = gerar(pasta, cena["variacoes"] if cena else None, cena["nome"] if cena else None)
            print(f"escolha: {len(d['opcoes'])} opção(ões) em {os.path.join(pasta, 'escolha.json')}; faltam "
                  f"{d['faltam_variacoes']} variação(ões)")
            for o in d["opcoes"]:
                print(f"  {o['opcao']}: t{o['n']} nota {o['nota']} vídeo {o['video'] or '(sem vídeo)'}")
        else:
            reg = escolher(pasta, argv[2])
            print(f"escolha registrada na biblioteca: {reg['id']} (assinatura {reg['assinatura']})")
    except ValueError as e:
        print(f"escolha: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
