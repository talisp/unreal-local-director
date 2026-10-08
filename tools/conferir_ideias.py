"""Confere um arquivo de ideias do "júnior" (linha 1, Fase 9; rotina em docs/rotinas/L1_JUNIOR.md). Sem Unreal.

Uso: .venv-ferramentas\\Scripts\\python.exe tools\\conferir_ideias.py ideias/<data>-<tema>.md
Imprime {ok, ideias:[{n, titulo, ok, motivos}], motivos} e sai com 0 só se o arquivo inteiro passou.

Formato (cada ideia é uma seção "## N. título"):
  - **Problema:** ...            obrigatório
  - **Ideia:** ...               obrigatório
  - **Evidência:** ...           obrigatório: `arquivo:linha` que EXISTE no repositório, ou um número com unidade
  - **Fonte:** <url> — "trecho"  obrigatório se veio da internet (link http(s) + trecho entre aspas)
  - **Biblioteca:** nome==versão  obrigatório se envolve biblioteca; a versão tem de ser a INSTALADA (pip freeze do
                                  venv\\ ou do .venv-ferramentas). Context7 é fonte auxiliar, não verdade.
  - **Custo:** baixo | médio | alto
Recusa: mais de 5 ideias, campo faltando, arquivo:linha inexistente, fonte sem trecho, biblioteca sem versão ou com
versão que não está instalada, e ideia repetida de um item de docs/PENDENCIAS.md.
"""
import json
import os
import re
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHONS = (os.path.join(RAIZ, "venv", "Scripts", "python.exe"), os.path.join(RAIZ, ".venv-ferramentas", "Scripts", "python.exe"))
MAX_IDEIAS = 5
SIMILARIDADE_REPETIDA = 0.6
ARQ_LINHA = re.compile(r"`?([\w./\\-]+\.\w+):(\d+)`?")
NUMERO = re.compile(r"\d+(?:[.,]\d+)?\s*(?:cm|mm|s|ms|min|%|°|graus|quadros|tentativas|vezes|trocas|casos)\b", re.I)


def _campos(bloco: str) -> dict:
    campos = {}
    for m in re.finditer(r"^\s*-\s*\*\*([^*:]+):\*\*\s*(.*)$", bloco, re.M):
        campos[m.group(1).strip().lower()] = m.group(2).strip()
    return campos


def instalados() -> dict:
    """{nome normalizado: {versões}} dos dois Pythons do projeto (pip freeze, só leitura)."""
    out = {}
    for py in PYTHONS:
        if not os.path.exists(py):
            continue
        r = subprocess.run([py, "-B", "-m", "pip", "freeze", "--disable-pip-version-check"], capture_output=True, timeout=120)
        for linha in r.stdout.decode("utf-8", "replace").splitlines():
            if "==" in linha:
                nome, ver = linha.split("==", 1)
                out.setdefault(nome.strip().lower().replace("_", "-"), set()).add(ver.strip())
    return out


def _palavras(t: str) -> set:
    return {w for w in re.findall(r"[a-zà-ú0-9_]{4,}", t.lower())}


def _pendencias() -> list:
    p = os.path.join(RAIZ, "docs", "PENDENCIAS.md")
    if not os.path.exists(p):
        return []
    out = []
    for linha in open(p, encoding="utf-8"):
        m = re.match(r"\|\s*(\d+)\s*\|[^|]*\|([^|]*)\|", linha)
        if m and "~~" not in m.group(2):  # item riscado (resolvido) não conta
            out.append((m.group(1), _palavras(m.group(2))))
    return out


def conferir_ideia(n: int, titulo: str, bloco: str, pacotes: dict, pendencias: list) -> dict:
    c, motivos = _campos(bloco), []
    for k in ("problema", "ideia", "evidência", "custo"):
        if not c.get(k):
            motivos.append(f"falta '{k.capitalize()}'")
    ev = c.get("evidência", "")
    refs = ARQ_LINHA.findall(ev)
    for arq, lin in refs:
        caminho = os.path.join(RAIZ, arq.replace("\\", "/"))
        if not os.path.isfile(caminho):
            motivos.append(f"evidência aponta arquivo inexistente: {arq}")
        elif int(lin) < 1 or int(lin) > sum(1 for _ in open(caminho, encoding="utf-8", errors="replace")):
            motivos.append(f"evidência aponta linha inexistente: {arq}:{lin}")
    if ev and not refs and not NUMERO.search(ev):
        motivos.append("evidência sem arquivo:linha nem número com unidade")
    if "fonte" in c and not (re.search(r"https?://\S+", c["fonte"]) and re.search(r"[\"“].{8,}[\"”]", c["fonte"])):
        motivos.append("fonte da internet sem link http(s) e trecho entre aspas")
    if "biblioteca" in c:
        m = re.search(r"([A-Za-z0-9_.-]+)\s*==\s*([0-9][\w.+-]*)", c["biblioteca"])
        if not m:
            motivos.append("biblioteca sem versão citada (nome==versão)")
        else:
            nome, ver = m.group(1).lower().replace("_", "-"), m.group(2)
            if ver not in pacotes.get(nome, set()):
                motivos.append(f"{m.group(1)}=={ver} não está instalado (instalado: {sorted(pacotes.get(nome, set())) or 'nada'})")
    if c.get("custo") and c["custo"].lower().split()[0] not in ("baixo", "médio", "medio", "alto"):
        motivos.append("custo tem de ser baixo, médio ou alto")
    texto = _palavras(titulo + " " + c.get("ideia", ""))
    for num, pal in pendencias:
        if texto and pal and len(texto & pal) / len(texto | pal) >= SIMILARIDADE_REPETIDA:
            motivos.append(f"repetida da pendência {num}")
    return {"n": n, "titulo": titulo, "ok": not motivos, "motivos": motivos}


def conferir(caminho: str, pacotes: dict | None = None) -> dict:
    texto = open(caminho, encoding="utf-8").read()
    partes = re.split(r"^##\s+(\d+)\.\s*(.*)$", texto, flags=re.M)
    ideias = [(int(partes[i]), partes[i + 1].strip(), partes[i + 2]) for i in range(1, len(partes) - 2, 3)]
    motivos = []
    if not ideias:
        motivos.append("nenhuma ideia no formato '## N. título'")
    if len(ideias) > MAX_IDEIAS:
        motivos.append(f"{len(ideias)} ideias: o máximo é {MAX_IDEIAS}")
    pacotes = instalados() if pacotes is None else pacotes
    pend = _pendencias()
    res = [conferir_ideia(n, t, b, pacotes, pend) for n, t, b in ideias]
    return {"ok": not motivos and all(r["ok"] for r in res), "ideias": res, "motivos": motivos}


def main(argv) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    r = conferir(argv[0])
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
