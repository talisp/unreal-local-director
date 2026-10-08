"""O painel das 4 linhas do Director: um comando para cada uma e o estado de todas.

Uso (na raiz):
  venv\\Scripts\\python.exe tools\\director.py              menu (pergunta o número)
  venv\\Scripts\\python.exe tools\\director.py estado       uma linha por linha de trabalho: último resultado e o que falta
  venv\\Scripts\\python.exe tools\\director.py junior [--tema N] [--seco]
  venv\\Scripts\\python.exe tools\\director.py bateria
  venv\\Scripts\\python.exe tools\\director.py unreal [--seco | --ensaio | --noite] [--cena cenas\\fila.md]
  venv\\Scripts\\python.exe tools\\director.py astra --tema T --pergunta "..." [--arquivos a,b] [--enviar --confirmo-cota]
O ensaio e a noite no Unreal, e o envio ao Astra, são decisões do operador (gastam Unreal ou cota).
"""
import glob
import json
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY_FERR = os.path.join(RAIZ, ".venv-ferramentas", "Scripts", "python.exe")
PY = os.path.join(RAIZ, "venv", "Scripts", "python.exe")
LINHAS = {"junior": (PY_FERR, "junior.py"), "bateria": (PY_FERR, "bateria.py"), "unreal": (PY, "linha2.py"),
          "astra": (PY_FERR, "astra.py")}


def _git(*a) -> str:
    r = subprocess.run(["git", *a], cwd=RAIZ, capture_output=True, timeout=30)
    return r.stdout.decode("utf-8", "replace").strip()


def _json(caminho: str):
    try:
        return json.load(open(caminho, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _mais_novo(padrao: str) -> str | None:
    xs = glob.glob(os.path.join(RAIZ, padrao))
    return max(xs, key=os.path.getmtime) if xs else None


def estado() -> list:
    """[(linha, situação em uma frase)]: só lê arquivos, não roda nada."""
    out = []
    head = _git("rev-parse", "--short=12", "HEAD")
    r = _json(os.path.join(RAIZ, "work", "bateria", head, "RESUMO.json"))
    out.append(("bateria", "não rodou no commit atual (rode: director.py bateria)" if not r else
                f"{'OK' if r['ok'] else 'FALHOU'} no commit {head}, marco {'aprovado' if r['marco_aprovado'] else 'não aprovado'}, "
                f"{r['duracao_s']} s"))
    j = _mais_novo(os.path.join("work", "junior", "*", "resumo.json"))
    jr = _json(j) if j else None
    out.append(("junior", "nunca rodou pelo comando (rode: director.py junior)" if not jr else
                f"{'OK' if jr['ok'] else 'COM PROBLEMA'}: tema {jr['tema']['n']} ({jr['tema']['tema']}), "
                f"{len(jr['ideias'])} ideias em {jr['arquivo']}; esperam o operador aprovar"))
    lan = _mais_novo(os.path.join("work", "*", "LANCAMENTO.json"))
    li = _json(lan) if lan else None
    if not li:
        out.append(("unreal", "ensaio ainda não lançado. Falta: o operador lançar 'director.py unreal --ensaio' (prova a "
                              "vigia); depois a noite"))
    else:
        pasta = os.path.dirname(lan)  # type: ignore[arg-type]
        n = sum(1 for ln in open(os.path.join(pasta, "tentativas.jsonl"), encoding="utf-8")
                if '"tipo_linha": "tentativa"' in ln) if os.path.exists(os.path.join(pasta, "tentativas.jsonl")) else 0
        fim = "fechamento escrito" if os.path.exists(os.path.join(pasta, "FECHAMENTO.md")) or \
            os.path.exists(os.path.join(pasta, "ENSAIO.md")) else "sem fechamento ainda"
        out.append(("unreal", f"{li['modo']} de {li['quando']} ({li['rodada']}): {n} tentativas, {fim}"))
    a = _mais_novo(os.path.join("escaladas", "*-ASTRA-*.md"))
    out.append(("astra", "nunca chamado (montar o pacote não gasta nada; enviar precisa do 'sim' do operador)" if not a else
                f"última revisão em {os.path.basename(a)}"))
    return out


def rodar(linha: str, args: list) -> int:
    py, script = LINHAS[linha]
    if linha == "unreal" and "--cena" not in args:
        args = args + ["--cena", os.path.join("cenas", "fila.md")]
    if linha == "unreal" and not any(x in args for x in ("--seco", "--ensaio", "--noite")):
        args = args + ["--seco"]
    return subprocess.run([py, os.path.join(RAIZ, "tools", script), *args], cwd=RAIZ).returncode


def main(argv) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if not argv:
        print("Director: 1 júnior · 2 bateria · 3 unreal (só gera o pedido; ensaio/noite: use os comandos) · "
              "4 astra (só o pacote) · 5 estado")
        escolha = input("número: ").strip()
        argv = {"1": ["junior"], "2": ["bateria"], "3": ["unreal", "--seco"], "4": ["astra", "--tema", "geral",
                "--pergunta", input("pergunta para o Astra: ").strip() if escolha == "4" else ""],
                "5": ["estado"]}.get(escolha, ["estado"])
    if argv[0] == "estado":
        for linha, txt in estado():
            print(f"{linha:8} {txt}")
        return 0
    if argv[0] not in LINHAS:
        print(__doc__)
        return 2
    return rodar(argv[0], argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
