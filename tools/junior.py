"""Linha 1, o júnior, num comando: tema -> pedido -> hermes-dev -> conferidor -> auditoria -> tema marcado.

Uso (na raiz):
  .venv-ferramentas\\Scripts\\python.exe tools\\junior.py            # próximo tema sem data de uso
  .venv-ferramentas\\Scripts\\python.exe tools\\junior.py --tema 3   # um tema da lista
  .venv-ferramentas\\Scripts\\python.exe tools\\junior.py --seco     # só monta e mostra o pedido (não chama o Hermes)
O Qwen roda pelo Hermes, no perfil hermes-dev (D27), com UNREAL_MACROS_OFFLINE=1; nada no perfil muda.
Grava work/junior/<data>-<tema>/ (pedido.md, sessao.jsonl, resumo.json). Sai com 0 só se o conferidor aprovou e a
auditoria não achou escrita fora de ideias/ nem uso da porta 8001.
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import unicodedata

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMAS = os.path.join(RAIZ, "docs", "rotinas", "temas.md")
ROTINA = os.path.join(RAIZ, "docs", "rotinas", "L1_JUNIOR.md")
HERMES = os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes", "bin", "hermes.cmd")
PY_FERR = os.path.join(RAIZ, ".venv-ferramentas", "Scripts", "python.exe")
RASCUNHO_HERMES = "hermes/profiles/hermes-dev/cache/scratch"
LINHA_TEMA = re.compile(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*$")


# ---------- temas ----------
def ler_temas(caminho: str = TEMAS) -> list:
    out = []
    for linha in open(caminho, encoding="utf-8"):
        m = LINHA_TEMA.match(linha.strip())
        if m and m.group(1).isdigit():
            out.append({"n": int(m.group(1)), "tema": m.group(2), "pergunta": m.group(3),
                        "usado": m.group(4) not in ("", "—", "-")})
    return out


def escolher_tema(temas: list, n: int | None = None) -> dict:
    if n is not None:
        for t in temas:
            if t["n"] == n:
                return t
        raise ValueError(f"tema {n} não está em temas.md (há {len(temas)})")
    livres = [t for t in temas if not t["usado"]]
    if not livres:
        raise ValueError("todos os temas já foram usados: acrescente temas em docs/rotinas/temas.md ou use --tema")
    return livres[0]


def slug(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    palavras = [p for p in re.findall(r"[a-z0-9]+", s) if p not in ("de", "da", "do", "e", "a", "o", "para", "por")]
    return "-".join(palavras[:3]) or "tema"


def marcar_tema(n: int, data: str, arquivo_rel: str, caminho: str = TEMAS) -> None:
    linhas = open(caminho, encoding="utf-8").read().split("\n")
    for i, linha in enumerate(linhas):
        m = LINHA_TEMA.match(linha.strip())
        if m and m.group(1) == str(n):
            usado = m.group(4)
            novo = f"{data[8:10]}/{data[5:7]} → [{arquivo_rel}](../../{arquivo_rel})"
            novo = novo if usado in ("", "—", "-") else f"{usado}; {novo}"
            linhas[i] = f"| {n} | {m.group(2)} | {m.group(3)} | {novo} |"
    open(caminho, "w", encoding="utf-8", newline="\n").write("\n".join(linhas))


# ---------- pedido ----------
def montar_pedido(tema: dict, data: str) -> tuple:
    """(texto do pedido, caminho relativo do arquivo de saída). Sai da rotina L1_JUNIOR, sem texto digitado à mão."""
    rotina = open(ROTINA, encoding="utf-8").read()
    corpo = rotina.split("## Pedido (preencha `<tema>` e `<data>`)", 1)[1]
    s = slug(tema["tema"])
    corpo = corpo.replace("sobre o tema **<tema>**", f"sobre o tema **{tema['tema']}** (pergunta-guia: {tema['pergunta']})")
    corpo = corpo.replace("<tema>", s).replace("<data>", data)
    cab = ("Pasta do repositório: <repo> (terminal Bash: barras normais, aspas). "
           f"Tema {tema['n']} de docs/rotinas/temas.md.\n")
    return cab + corpo, f"ideias/{data}-{s}.md"


# ---------- auditoria da sessão ----------
def auditar(eventos: list, raiz: str = RAIZ) -> dict:
    """O que a sessão fez de fato: escritas fora de ideias/ (rascunho do próprio Hermes vale) e comandos que citam a
    porta 8001 ou o cliente do Unreal (texto de documento lido não conta: só a entrada das ações)."""
    acoes, fora, unreal = 0, [], []
    base = raiz.replace("\\", "/").lower()
    for e in eventos:
        if e.get("type") != "tool_use":
            continue
        acoes += 1
        nome, ent = e.get("name", ""), e.get("input") or {}
        if nome in ("write_file", "patch"):
            p = str(ent.get("path", "")).replace("\\", "/")
            dentro = p.lower().startswith(base + "/ideias/") or p.lower().startswith("ideias/")
            if not dentro and RASCUNHO_HERMES not in p.lower():
                fora.append(p)
        comando = json.dumps(ent, ensure_ascii=False)
        # só o que EXECUTA conta: link de documentação ("unreal-engine" no endereço) ou texto escrito não é acesso
        if nome in ("terminal", "execute_code") and re.search(r"8001|mcp_client|chamada_avancada", comando):
            unreal.append(f"{nome}: {comando[:120]}")
        if nome.startswith("mcp__florentia") or nome.startswith("mcp__unreal"):
            unreal.append(nome)
    return {"acoes": acoes, "escritas_fora": fora, "unreal": unreal}


def ler_eventos(caminho: str) -> tuple:
    eventos, final = [], {}
    for linha in open(caminho, encoding="utf-8", errors="replace"):
        try:
            e = json.loads(linha)
        except ValueError:
            continue
        eventos.append(e)
        if e.get("type") == "result":
            final = e
    return eventos, final


def chamar_hermes(pedido: str, log: str, prazo_s: int = 1800) -> int:
    env = dict(os.environ, UNREAL_MACROS_OFFLINE="1")
    with open(log, "w", encoding="utf-8") as saida:
        r = subprocess.run(["cmd", "/c", HERMES, "-p", "hermes-dev", "chat", "--query-file", pedido, "--format", "stream-json",
                            "--max-turns", "60", "--run-budget", str(prazo_s), "--in", RAIZ],
                           stdout=saida, stderr=subprocess.DEVNULL, env=env, timeout=prazo_s + 300)
    return r.returncode


def conferir(arquivo: str) -> dict:
    r = subprocess.run([PY_FERR, os.path.join(RAIZ, "tools", "conferir_ideias.py"), arquivo], capture_output=True,
                       cwd=RAIZ, timeout=300)
    try:
        return json.loads(r.stdout.decode("utf-8"))
    except ValueError:
        return {"ok": False, "ideias": [], "motivos": [f"conferidor não rodou: {r.stderr.decode('utf-8', 'replace')[-200:]}"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="linha 1: o júnior")
    ap.add_argument("--tema", type=int)
    ap.add_argument("--seco", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    data = dt.date.today().isoformat()
    tema = escolher_tema(ler_temas(), a.tema)
    pedido, saida_rel = montar_pedido(tema, data)
    pasta = os.path.join(RAIZ, "work", "junior", f"{data}-{slug(tema['tema'])}")
    os.makedirs(pasta, exist_ok=True)
    arq_pedido = os.path.join(pasta, "pedido.md")
    open(arq_pedido, "w", encoding="utf-8", newline="\n").write(pedido)
    if a.seco:
        print(f"júnior (seco): tema {tema['n']} \"{tema['tema']}\" → {saida_rel}; pedido em {arq_pedido}")
        return 0
    t0 = time.time()
    codigo = chamar_hermes(arq_pedido, os.path.join(pasta, "sessao.jsonl"))
    eventos, final = ler_eventos(os.path.join(pasta, "sessao.jsonl"))
    aud = auditar(eventos)
    saida = os.path.join(RAIZ, saida_rel)
    conf = conferir(saida) if os.path.exists(saida) else {"ok": False, "ideias": [], "motivos": ["arquivo de ideias não foi escrito"]}
    if os.path.exists(saida):
        marcar_tema(tema["n"], data, saida_rel)
    ok = codigo == 0 and conf["ok"] and not aud["escritas_fora"] and not aud["unreal"]
    resumo = {"ok": ok, "tema": tema, "arquivo": saida_rel, "sessao": final.get("session_id"), "saida_hermes": codigo,
              "minutos": round((time.time() - t0) / 60, 1), "auditoria": aud, "conferidor": conf,
              "ideias": [(i["n"], i["titulo"], i["ok"]) for i in conf.get("ideias", [])]}
    json.dump(resumo, open(os.path.join(pasta, "resumo.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"júnior {'OK' if ok else 'COM PROBLEMA'} · tema {tema['n']} · {saida_rel} · {len(resumo['ideias'])} ideias "
          f"(conferidor {'ok' if conf['ok'] else 'reprovou'}) · {aud['acoes']} ações · {resumo['minutos']} min")
    for n, titulo, i_ok in resumo["ideias"]:
        print(f"  {n}. {titulo} {'' if i_ok else '(reprovada)'}")
    for p in aud["escritas_fora"]:
        print(f"  ! escreveu fora de ideias/: {p}")
    for u in aud["unreal"]:
        print(f"  ! Unreal: {u}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
