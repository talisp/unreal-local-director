"""Linha 3, o Astra (Codex), num comando: pacote montado por script -> (com o "sim" do operador) Codex só leitura ->
resposta conferida -> escaladas/<data>-ASTRA-<tema>.md.

Uso (na raiz):
  .venv-ferramentas\\Scripts\\python.exe tools\\astra.py --tema fase8 --pergunta "O pedido da Fase 8 tem furo?" [--arquivos a.md,b.py]
      só monta o pacote e mostra o tamanho (NÃO gasta cota)
  ... --enviar --confirmo-cota
      chama pelo hermes-dev (D27), que roda `codex exec -s read-only`; precisa do "sim" do operador a cada vez
  ... --conferir <resposta.md>
      só confere uma resposta já recebida e grava o arquivo em escaladas/
O pacote sai de script (nada digitado por LLM): commit-base, mudança desde a última revisão do Astra, RESUMO da
bateria, números do HANDOFF e pendências abertas; tamanho máximo PACOTE_MAX.
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROTINA = os.path.join(RAIZ, "docs", "rotinas", "L3_ASTRA.md")
HERMES = os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes", "bin", "hermes.cmd")
PACOTE_MAX = 14000  # caracteres; seção que estoura é cortada com aviso
SECAO_MAX = 4000
GRAVIDADES = ("alta", "media", "baixa")


def git(*args) -> str:
    r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, timeout=60)
    return r.stdout.decode("utf-8", "replace").strip() if r.returncode == 0 else ""


def ultima_revisao() -> str | None:
    """Commit revisado na última resposta do Astra (linha 'Commit revisado: `hash`' em escaladas/*-ASTRA-*.md)."""
    pasta = os.path.join(RAIZ, "escaladas")
    for nome in sorted((n for n in os.listdir(pasta) if "-ASTRA-" in n), reverse=True):
        m = re.search(r"Commit revisado:\s*`([0-9a-f]{7,40})`", open(os.path.join(pasta, nome), encoding="utf-8").read())
        if m:
            return m.group(1)
    return None


def _corta(texto: str, limite: int = SECAO_MAX) -> str:
    return texto if len(texto) <= limite else texto[:limite] + f"\n[... cortado: {len(texto) - limite} caracteres a mais]"


def _secao_numeros() -> str:
    h = open(os.path.join(RAIZ, "docs", "HANDOFF.md"), encoding="utf-8").read()
    m = re.search(r"## Números que valem\n(.*?)(?:\n## |\Z)", h, re.S)
    return m.group(1).strip() if m else "(seção 'Números que valem' não achada no HANDOFF)"


def _pendencias_abertas() -> str:
    linhas = [ln for ln in open(os.path.join(RAIZ, "docs", "PENDENCIAS.md"), encoding="utf-8")
              if re.match(r"\|\s*\d+\s*\|", ln) and "~~" not in ln]
    return "".join(linhas).strip() or "(nenhuma)"


def montar_pacote(pergunta: str, arquivos: list, base: str | None = None, resumo_bateria: str | None = None) -> str:
    if not pergunta.strip():
        raise ValueError("falta a pergunta: o Astra responde UMA pergunta por chamada")
    head = git("rev-parse", "--short=12", "HEAD")
    base = base or ultima_revisao()
    if base:
        mudanca = f"Commits desde `{base}`:\n" + git("log", "--oneline", f"{base}..HEAD") + "\n\nArquivos:\n" + \
                  git("diff", "--stat", f"{base}..HEAD")
    else:
        mudanca = "(primeira revisão do Astra: últimos 20 commits)\n" + git("log", "--oneline", "-20")
    if resumo_bateria is None:
        caminho = os.path.join(RAIZ, "work", "bateria", head, "RESUMO.json")
        resumo_bateria = open(caminho, encoding="utf-8").read() if os.path.exists(caminho) else \
            f"(a bateria não rodou no commit {head}: rode tools/bateria.py antes de enviar)"
    faltam = [a for a in arquivos if not os.path.exists(os.path.join(RAIZ, a))]
    if faltam:
        raise ValueError(f"arquivos que não existem: {faltam}")
    partes = [f"## A pergunta\n{pergunta.strip()}",
              f"## Commit-base (o que você revisa)\n`{head}`",
              "## Arquivos que você pode abrir\n" + ("\n".join(f"- {a}" for a in arquivos) or "- (nenhum além deste pacote)"),
              "## Mudança desde a última revisão\n" + _corta(mudanca),
              "## Bateria neste commit (RESUMO.json)\n" + _corta(resumo_bateria),
              "## Números que valem (HANDOFF)\n" + _corta(_secao_numeros()),
              "## Pendências abertas (PENDENCIAS.md)\n" + _corta(_pendencias_abertas())]
    pacote = "\n\n".join(partes)
    if len(pacote) > PACOTE_MAX:
        pacote = pacote[:PACOTE_MAX] + f"\n[... pacote cortado em {PACOTE_MAX} caracteres]"
    return pacote


def montar_pedido(pacote: str) -> str:
    rotina = open(ROTINA, encoding="utf-8").read()
    corpo = rotina.split("## Pedido ao Astra (o script cola o pacote no fim)", 1)[1].strip()
    return corpo + "\n\n---\n# Pacote\n\n" + pacote


# ---------- resposta ----------
def conferir_resposta(texto: str, raiz: str = RAIZ) -> dict:
    blocos = re.findall(r"```json\s*(\{.*?\})\s*```", texto, re.S)
    if not blocos:
        return {"ok": False, "motivos": ["sem bloco ```json``` no fim da resposta"], "achados": []}
    try:
        d = json.loads(blocos[-1])
    except ValueError as e:
        return {"ok": False, "motivos": [f"bloco JSON ilegível: {e}"], "achados": []}
    motivos, achados = [], []
    if not isinstance(d.get("achados"), list):
        return {"ok": False, "motivos": ["'achados' tem de ser uma lista"], "achados": []}
    for i, a in enumerate(d["achados"], 1):
        m = []
        for k in ("achado", "gravidade", "prova", "correcao", "verificado"):
            if k not in a or a[k] in ("", None):
                m.append(f"falta '{k}'")
        if a.get("gravidade") not in GRAVIDADES:
            m.append(f"gravidade tem de ser {GRAVIDADES}")
        prova = re.match(r"\s*`?([^:`]+\.\w+):(\d+)", str(a.get("prova", "")))
        if not prova:
            m.append("prova sem arquivo:linha")
        else:
            arq = os.path.join(raiz, prova.group(1).strip().replace("\\", "/"))
            if not os.path.isfile(arq):
                m.append(f"prova aponta arquivo inexistente: {prova.group(1)}")
            elif int(prova.group(2)) > sum(1 for _ in open(arq, encoding="utf-8", errors="replace")):
                m.append(f"prova aponta linha inexistente: {prova.group(1)}:{prova.group(2)}")
        if not isinstance(a.get("verificado"), bool):
            m.append("'verificado' tem de ser true ou false")
        achados.append({"n": i, "achado": a.get("achado"), "gravidade": a.get("gravidade"), "prova": a.get("prova"),
                        "ok": not m, "motivos": m})
        motivos += [f"achado {i}: {x}" for x in m]
    return {"ok": not motivos, "motivos": motivos, "achados": achados, "resumo": d.get("resumo"), "pergunta": d.get("pergunta")}


def gravar_escalada(tema: str, pergunta: str, commit: str, resposta: str, conf: dict, data: str | None = None) -> str:
    data = data or dt.date.today().isoformat()
    rel = f"escaladas/{data}-ASTRA-{tema}.md"
    linhas = [f"# Astra: {tema} ({data})", "", f"Commit revisado: `{commit}`", f"Pergunta: {pergunta}",
              f"Formato conferido: {'ok' if conf['ok'] else 'COM PROBLEMA: ' + '; '.join(conf['motivos'])}", "",
              "| # | Gravidade | Achado | Prova | Formato |", "|---|---|---|---|---|"]
    for a in conf["achados"]:
        linhas.append(f"| {a['n']} | {a['gravidade']} | {a['achado']} | `{a['prova']}` | {'ok' if a['ok'] else 'reprovado'} |")
    linhas += ["", "**Mapa (Claude preenche):** para cada achado, onde ele foi parar (skill, lição, código, pendência).", "",
               "## Resposta completa", "", resposta]
    open(os.path.join(RAIZ, rel), "w", encoding="utf-8", newline="\n").write("\n".join(linhas) + "\n")
    return rel


def enviar(pedido_path: str, saida_path: str) -> int:
    """hermes-dev roda UM comando: codex exec só leitura, com a resposta em arquivo."""
    instrucao = os.path.join(os.path.dirname(pedido_path), "instrucao_hermes.md")
    cmd = (f'codex exec -s read-only -C "{RAIZ}" -o "{saida_path}" --skip-git-repo-check < "{pedido_path}"').replace("\\", "/")
    open(instrucao, "w", encoding="utf-8", newline="\n").write(
        "Use a skill codex. Rode EXATAMENTE este comando no terminal, uma vez, e espere terminar (pode levar minutos):\n\n"
        f"{cmd}\n\nNão rode mais nada, não edite arquivos, não use o Unreal. Responda só: 'feito' ou o erro.\n")
    r = subprocess.run(["cmd", "/c", HERMES, "-p", "hermes-dev", "chat", "--query-file", instrucao, "-Q",
                        "--max-turns", "8", "--run-budget", "1800", "--in", RAIZ],
                       capture_output=True, env=dict(os.environ, UNREAL_MACROS_OFFLINE="1"), timeout=2100)
    return r.returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="linha 3: o Astra")
    ap.add_argument("--tema", required=True)
    ap.add_argument("--pergunta", default="")
    ap.add_argument("--arquivos", default="")
    ap.add_argument("--base")
    ap.add_argument("--enviar", action="store_true")
    ap.add_argument("--confirmo-cota", action="store_true")
    ap.add_argument("--conferir")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    data = dt.date.today().isoformat()
    pasta = os.path.join(RAIZ, "work", "astra", f"{data}-{a.tema}")
    os.makedirs(pasta, exist_ok=True)
    commit = git("rev-parse", "--short=12", "HEAD")
    if a.conferir:
        resposta = open(a.conferir, encoding="utf-8").read()
        conf = conferir_resposta(resposta)
        rel = gravar_escalada(a.tema, a.pergunta or conf.get("pergunta") or "", commit, resposta, conf, data)
        print(f"astra: resposta {'ok' if conf['ok'] else 'COM PROBLEMA'} · {len(conf['achados'])} achado(s) · {rel}")
        for m in conf["motivos"]:
            print(f"  ! {m}")
        return 0 if conf["ok"] else 1
    arquivos = [x.strip() for x in a.arquivos.split(",") if x.strip()]
    pedido = montar_pedido(montar_pacote(a.pergunta, arquivos, a.base))
    arq_pedido = os.path.join(pasta, "pedido.md")
    open(arq_pedido, "w", encoding="utf-8", newline="\n").write(pedido)
    if not a.enviar:
        print(f"astra (só o pacote, sem gastar cota): {len(pedido)} caracteres · {arq_pedido}")
        return 0
    if not a.confirmo_cota:
        print("astra: --enviar gasta cota do Codex; precisa do 'sim' do operador e de --confirmo-cota")
        return 2
    login = subprocess.run(["codex", "login", "status"], capture_output=True, timeout=60, shell=True)
    if b"Logged in" not in login.stdout + login.stderr:
        print(f"astra: Codex CLI sem login ({(login.stdout + login.stderr).decode('utf-8', 'replace').strip()[:120]})")
        return 1
    saida = os.path.join(pasta, "resposta.md")
    codigo = enviar(arq_pedido, saida)
    if not os.path.exists(saida):
        print(f"astra: o Codex não gravou a resposta (hermes saiu com {codigo})")
        return 1
    return main(["--tema", a.tema, "--pergunta", a.pergunta, "--conferir", saida])


if __name__ == "__main__":
    sys.exit(main())
