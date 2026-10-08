"""Bateria de quebra (Fase 2a do PLANO_PROXIMA_VERSAO): um comando, uma linha de resumo e um JSON curto.

Etapas, em ordem, num worktree do commit testado (nunca na pasta do Runtime):
  ruff, basedpyright  contra a linha de base de 07/10 (tools/bateria_base.json): acusa só o que é NOVO;
  suite:<nome>        as 4 suítes sem Unreal, no .venv-ferramentas, com trava isolada; 0 casos conta como falha;
  propriedades        src/testes_propriedades.py (pytest + Hypothesis): falha = defeito NOVO; os conhecidos
                      (tools/bateria_conhecidos.json) são pulados e listados no campo `conhecidos`;
  ambiente            porta 8001 e trava iguais antes e depois (só leitura: netstat e o arquivo da trava);
  venv_runtime        sha256 do `pip freeze` do venv\\ do Runtime igual antes e depois (fica no detalhe);
  worktree           o worktree criado foi removido e não aparece em `git worktree list`.
Todo subprocesso recebe UNREAL_MACROS_OFFLINE=1 (o cliente da 8001 recusa conectar). Não usa o Unreal.

Saída: work/bateria/<commit>/RESUMO.json = {ok, etapas:[{nome, ok, novos, detalhe_curto}], duracao_s, commit,
       conhecidos:[{id, contrato, condicao, o_que, decisao_talis}], marco_aprovado}; e contraexemplos.json.
marco_aprovado = tudo passou E nenhum conhecido com decisao_talis "pendente".
Código de saída 0 só se todas as etapas passaram.

Uso:  .venv-ferramentas\\Scripts\\python.exe tools\\bateria.py [--commit HEAD]
      --pasta <cópia>   roda numa cópia já pronta, sem worktree (teste do aviso plantado)
      --saida <pasta>   onde gravar o RESUMO.json
      --gerar-base <pasta dos checadores de 07/10>   reescreve tools/bateria_base.json a partir das saídas brutas
"""
import argparse
import collections
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FERR = os.path.join(RAIZ, ".venv-ferramentas", "Scripts")
BASE = os.path.join(RAIZ, "tools", "bateria_base.json")
STUBS = os.path.join(RAIZ, "work", "stubs")
TRAVA = os.environ.get("UNREAL_MACROS_TRAVA") or os.path.join(RAIZ, "work", "unreal.trava")
PRAZO_S = 300
PRAZO_SUITE_S = 120
PY_FERR = os.path.join(FERR, "python.exe")
PY_RUNTIME = os.path.join(RAIZ, "venv", "Scripts", "python.exe")
SUITES = ("testes_diario", "testes_bloco2", "testes_v003_bloco1", "testes_v003_blocos",
          "testes_biblioteca", "testes_fila", "testes_fila_executor", "testes_vigia_dev",
          "testes_offline", "testes_receita", "testes_ideias",
          "testes_junior", "testes_astra", "testes_cena", "testes_director",
          "testes_rotina")  # sem Unreal (nenhuma abre a 8001)


def env_offline() -> dict:
    env = dict(os.environ)
    env["UNREAL_MACROS_OFFLINE"] = "1"
    return env


def _rodar(cmd, cwd=RAIZ, prazo=PRAZO_S, extra=None):
    env = env_offline()
    env.update(extra or {})
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, timeout=prazo)


def git(*args, cwd=RAIZ) -> str:
    r = _rodar(["git", *args], cwd=cwd, prazo=60)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.decode('utf-8', 'replace').strip()[:300]}")
    return r.stdout.decode("utf-8", "replace").strip()


# ---------- ambiente (só leitura) ----------

def porta_escutando(saida_netstat: str, porta: int = 8001) -> bool:
    # Linha "TCP  127.0.0.1:8001  0.0.0.0:0  LISTENING  pid". O nome do estado muda com o idioma do Windows;
    # o endereço externo ":0" não muda e só aparece em quem está escutando.
    for linha in saida_netstat.splitlines():
        partes = linha.split()
        if len(partes) >= 3 and partes[0].upper() == "TCP" and partes[1].endswith(f":{porta}") and partes[2].endswith(":0"):
            return True
    return False


def estado_trava() -> str:
    if not os.path.exists(TRAVA):
        return "livre"
    try:
        info = json.load(open(TRAVA, encoding="utf-8"))
        return f"ocupada (pid {info.get('pid')})"
    except (OSError, ValueError):
        return "ocupada (ilegível)"


def estado_ambiente() -> dict:
    r = _rodar(["netstat", "-ano", "-p", "TCP"], prazo=30)
    texto = r.stdout.decode("utf-8", "replace")
    return {"porta_8001": "aberta" if porta_escutando(texto) else "fechada", "trava": estado_trava()}


# ---------- checadores contra a linha de base ----------

def _rel(caminho: str, pasta: str) -> str:
    return os.path.relpath(caminho, pasta).replace("\\", "/")


def contar_ruff(pasta: str) -> collections.Counter:
    r = _rodar([os.path.join(FERR, "ruff.exe"), "check", "--no-cache", "--exit-zero", "--output-format", "json"], cwd=pasta)
    if r.returncode != 0:
        raise RuntimeError("ruff não rodou: " + r.stderr.decode("utf-8", "replace").strip()[:200])
    return collections.Counter(f"{_rel(d['filename'], pasta)}|{d['code']}" for d in json.loads(r.stdout.decode("utf-8-sig")))


def contar_pyright(pasta: str) -> collections.Counter:
    if not os.path.exists(os.path.join(STUBS, "unreal.py")):
        raise RuntimeError(f"stubs do Unreal ausentes em {STUBS}: a linha de base 228+1 depende deles")
    cfg = json.load(open(os.path.join(pasta, "pyrightconfig.json"), encoding="utf-8"))
    p = pasta.replace("\\", "/")
    # A configuração do repositório aponta o venv e os stubs por caminho relativo, que não existem no worktree
    # (são ignorados pelo git). Esta cópia aponta para os da pasta única e fica FORA da pasta testada.
    cfg["include"] = [f"{p}/{x}" for x in cfg["include"]]
    cfg["exclude"] = [x if x.startswith("**") else f"{p}/{x}" for x in cfg["exclude"]]
    cfg["venvPath"], cfg["extraPaths"] = RAIZ.replace("\\", "/"), [STUBS.replace("\\", "/")]
    # Sem isto a raiz vira a pasta da configuração (temporária) e os imports locais somem (67 "novos" falsos, 08/10).
    cfg["executionEnvironments"] = [{"root": p, "extraPaths": [STUBS.replace("\\", "/")]}]
    tmp = tempfile.mkdtemp(prefix="bateria_pyright_")
    try:
        caminho_cfg = os.path.join(tmp, "pyrightconfig.json")
        json.dump(cfg, open(caminho_cfg, "w", encoding="utf-8"))
        r = _rodar([os.path.join(FERR, "basedpyright.exe"), "--outputjson", "--project", caminho_cfg], cwd=pasta)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    try:
        d = json.loads(r.stdout.decode("utf-8-sig"))
    except ValueError:
        raise RuntimeError("basedpyright não rodou: " + (r.stderr or r.stdout).decode("utf-8", "replace").strip()[:200])
    if not d["summary"]["filesAnalyzed"]:
        raise RuntimeError("basedpyright analisou 0 arquivos")  # 0 analisados daria "0 novos" sem ter olhado nada
    return collections.Counter(f"{_rel(x['file'], pasta)}|{x['severity']}|{x.get('rule', '')}" for x in d["generalDiagnostics"])


def comparar(nome: str, atual: collections.Counter, base: dict) -> dict:
    novos = {k: n - base.get(k, 0) for k, n in atual.items() if n > base.get(k, 0)}
    total_novos = sum(novos.values())
    detalhe = f"{sum(atual.values())} no total (base {sum(base.values())}), {total_novos} novos"
    if novos:
        detalhe += ": " + "; ".join(f"{k} +{n}" for k, n in sorted(novos.items())[:3]) + (" ..." if len(novos) > 3 else "")
    return {"nome": nome, "ok": total_novos == 0, "novos": total_novos, "detalhe_curto": detalhe}


def etapa_checador(nome: str, contar, pasta: str, base: dict) -> dict:
    try:
        return comparar(nome, contar(pasta), base.get(nome, {}))
    except Exception as e:  # noqa: BLE001 - checador que não roda é falha da etapa, não "0 novos"
        return {"nome": nome, "ok": False, "novos": 0, "detalhe_curto": f"não rodou: {str(e)[:200]}"}


# ---------- linha de base (gerada uma vez das saídas brutas de 07/10) ----------

def gerar_base(pasta_checadores: str) -> dict:
    ruff = collections.Counter()
    for linha in open(os.path.join(pasta_checadores, "ruff_completo.txt"), encoding="utf-8-sig"):
        m = re.match(r"(.+?):\d+:\d+: ([A-Z]+\d+) ", linha.strip())
        if m:
            ruff[f"{m.group(1).replace(chr(92), '/')}|{m.group(2)}"] += 1
    d = json.load(open(os.path.join(pasta_checadores, "basedpyright_com_stubs.json"), encoding="utf-8-sig"))
    pyright = collections.Counter()
    for x in d["generalDiagnostics"]:
        arquivo = re.sub(r".*unreal-macros(-v002)?[\\/]", "", x["file"]).replace("\\", "/")
        pyright[f"{arquivo}|{x['severity']}|{x.get('rule', '')}"] += 1
    return {"origem": "saídas brutas de 07/10 (work/harness_E4/checadores: ruff_completo.txt, basedpyright_com_stubs.json)",
            "ruff": dict(sorted(ruff.items())), "basedpyright": dict(sorted(pyright.items()))}


# ---------- as 4 suítes sem Unreal e o venv do Runtime ----------

def avaliar_suite(nome: str, codigo_saida: int, texto: str) -> dict:
    # O rodapé de cada suíte termina em "<nome>: P/T". Rodada vazia (0/0) sai com 0 e por isso conta como falha.
    linhas = [x.strip() for x in texto.splitlines() if x.strip()]
    ultima = linhas[-1] if linhas else ""
    m = re.search(r"(\d+)\s*/\s*(\d+)$", ultima)
    passou, total = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    ok = codigo_saida == 0 and m is not None and total > 0 and passou == total
    if ok:
        detalhe = f"{passou}/{total} casos"
    elif m and total == 0:
        detalhe = f"0 casos (saiu com {codigo_saida}): rodada vazia conta como falha"
    elif m:
        falhas = [x for x in linhas if x.startswith("FALHA")][:1]  # "FALHA" (bloco2) e "FALHOU"
        detalhe = f"{passou}/{total} casos, saiu com {codigo_saida}" + (f"; {falhas[0][:150]}" if falhas else "")
    else:
        detalhe = f"saiu com {codigo_saida} sem contagem; última linha: {ultima[:150]}"
    return {"nome": f"suite:{nome}", "ok": ok, "novos": 0 if ok else max(1, total - passou), "detalhe_curto": detalhe}


def rodar_suite(pasta: str, nome: str, trava_isolada: str) -> dict:
    # Python do .venv-ferramentas, -B (sem __pycache__ no worktree), offline e com uma trava só desta execução:
    # nem por engano uma suíte encosta na trava do Runtime.
    try:
        r = _rodar([PY_FERR, "-B", f"{nome}.py"], cwd=os.path.join(pasta, "src"), prazo=PRAZO_SUITE_S,
                   extra={"UNREAL_MACROS_TRAVA": trava_isolada, "PYTHONIOENCODING": "utf-8"})
    except subprocess.TimeoutExpired:
        return {"nome": f"suite:{nome}", "ok": False, "novos": 1, "detalhe_curto": f"passou de {PRAZO_SUITE_S} s"}
    return avaliar_suite(nome, r.returncode, (r.stdout + b"\n" + r.stderr).decode("utf-8", "replace"))


def hash_pip_runtime() -> str:
    # Só leitura: `pip freeze` do venv\ do Runtime (-B: não grava bytecode lá).
    try:
        r = _rodar([PY_RUNTIME, "-B", "-m", "pip", "freeze", "--disable-pip-version-check"], prazo=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"erro: {str(e)[:100]}"
    if r.returncode != 0:
        return f"erro: pip freeze saiu com {r.returncode}"
    return hashlib.sha256(r.stdout).hexdigest()


# ---------- propriedades (Hypothesis) e defeitos conhecidos ----------

def ler_junit(caminho: str) -> tuple:
    """(casos, falhas) de um junit XML do pytest; falhas = [{propriedade, mensagem}]. Casos pulados não contam."""
    import xml.etree.ElementTree as ET
    casos, falhas = 0, []
    for tc in ET.parse(caminho).getroot().iter("testcase"):
        if tc.find("skipped") is not None:
            continue
        casos += 1
        erro = tc.find("failure")
        if erro is None:
            erro = tc.find("error")
        if erro is not None:
            msg = (erro.get("message") or erro.text or "").strip().splitlines()
            falhas.append({"propriedade": tc.get("name"), "mensagem": (msg[0] if msg else "")[:300]})
    return casos, falhas


def rodar_propriedades(pasta: str, trava_isolada: str, destino: str) -> tuple:
    """Roda src/testes_propriedades.py (pytest + Hypothesis, semente fixa). O defeito conhecido é pulado lá dentro;
    toda falha que sobra é defeito NOVO. Grava contraexemplos.json em `destino`. Devolve (etapa, conhecidos)."""
    t0 = time.time()
    lista = os.environ.get("BATERIA_CONHECIDOS") or os.path.join(pasta, "tools", "bateria_conhecidos.json")
    try:
        conhecidos = json.load(open(lista, encoding="utf-8")) if os.path.exists(lista) else []
    except ValueError as e:
        return {"nome": "propriedades", "ok": False, "novos": 1, "detalhe_curto": f"lista de conhecidos ilegível: {e}"}, []
    resumo_conhecidos = [{k: c.get(k) for k in ("id", "contrato", "condicao", "o_que", "decisao_talis")} for c in conhecidos]
    tmp = tempfile.mkdtemp(prefix="bateria_prop_")
    junit = os.path.join(tmp, "junit.xml")
    try:
        try:
            r = _rodar([PY_FERR, "-B", "-m", "pytest", os.path.join("src", "testes_propriedades.py"), "-q",
                        "-p", "no:cacheprovider", f"--junitxml={junit}"], cwd=pasta, prazo=PRAZO_SUITE_S,
                       extra={"UNREAL_MACROS_TRAVA": trava_isolada, "PYTHONIOENCODING": "utf-8",
                              "BATERIA_CONHECIDOS": lista,
                              # o cache do Hypothesis (.hypothesis/) vai para a pasta temporária, não para a testada
                              "HYPOTHESIS_STORAGE_DIRECTORY": os.path.join(tmp, "hypothesis")})
        except subprocess.TimeoutExpired:
            return ({"nome": "propriedades", "ok": False, "novos": 1, "detalhe_curto": f"passou de {PRAZO_SUITE_S} s"},
                    resumo_conhecidos)
        if not os.path.exists(junit):
            saida = (r.stdout + r.stderr).decode("utf-8", "replace").strip().splitlines()
            return ({"nome": "propriedades", "ok": False, "novos": 1,
                     "detalhe_curto": f"pytest saiu com {r.returncode} sem relatório: {(saida or [''])[-1][:150]}"},
                    resumo_conhecidos)
        casos, falhas = ler_junit(junit)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    json.dump(falhas, open(os.path.join(destino, "contraexemplos.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ok = r.returncode == 0 and casos > 0 and not falhas
    if casos == 0:
        detalhe = "0 casos: rodada vazia conta como falha"
    else:
        detalhe = f"{casos - len(falhas)}/{casos} casos em {time.time() - t0:.1f} s; {len(conhecidos)} conhecidos pulados"
        if falhas:
            detalhe += "; " + " | ".join(f"{f['propriedade']}: {f['mensagem'][:90]}" for f in falhas[:3])
    novos = len(falhas) if falhas else (0 if ok else 1)
    return {"nome": "propriedades", "ok": ok, "novos": novos, "detalhe_curto": detalhe}, resumo_conhecidos


# ---------- worktree ----------

def criar_worktree(commit: str):
    tmp = tempfile.mkdtemp(prefix="bateria_wt_")
    wt = os.path.join(tmp, "wt")
    git("worktree", "add", "--detach", wt, commit)
    return tmp, wt


def remover_worktree(tmp: str, wt: str) -> dict:
    # Remove SÓ o worktree que esta execução criou, pelo caminho exato. Nunca `git worktree prune`.
    erro = ""
    try:
        git("worktree", "remove", wt)
    except RuntimeError:
        try:
            git("worktree", "remove", "--force", wt)  # sobrou arquivo que um checador criou; o worktree é nosso
        except RuntimeError as e:
            erro = str(e)[:150]
    shutil.rmtree(tmp, ignore_errors=True)
    alvo = os.path.normcase(os.path.abspath(wt))
    listados = [os.path.normcase(os.path.abspath(linha[9:])) for linha in git("worktree", "list", "--porcelain").splitlines()
                if linha.startswith("worktree ")]
    sobrou = alvo in listados or os.path.exists(wt)
    return {"nome": "worktree", "ok": not sobrou and not erro, "novos": int(sobrou),
            "detalhe_curto": f"sobrou {wt} {erro}".strip() if sobrou or erro else "removido; não aparece em git worktree list"}


# ---------- principal ----------

def rodar(commit: str = "HEAD", pasta: str | None = None, saida: str | None = None) -> dict:
    t0 = time.time()
    base = json.load(open(BASE, encoding="utf-8"))
    amb0 = estado_ambiente()
    pip0 = hash_pip_runtime()
    if pasta:
        id_commit, tmp, wt = f"pasta-{os.path.basename(os.path.abspath(pasta))}", None, os.path.abspath(pasta)
    else:
        id_commit = git("rev-parse", "--short=12", commit)
        tmp, wt = criar_worktree(id_commit)
    destino = saida or os.path.join(RAIZ, "work", "bateria", id_commit)
    os.makedirs(destino, exist_ok=True)
    etapas, conhecidos = [], []
    tmp_trava = tempfile.mkdtemp(prefix="bateria_trava_")
    try:
        etapas.append(etapa_checador("ruff", contar_ruff, wt, base))
        etapas.append(etapa_checador("basedpyright", contar_pyright, wt, base))
        for nome in SUITES:
            etapas.append(rodar_suite(wt, nome, os.path.join(tmp_trava, "unreal.trava")))
        etapa_prop, conhecidos = rodar_propriedades(wt, os.path.join(tmp_trava, "unreal.trava"), destino)
        etapas.append(etapa_prop)
    finally:
        fim_wt = remover_worktree(tmp, wt) if tmp else None
        shutil.rmtree(tmp_trava, ignore_errors=True)
    amb1 = estado_ambiente()
    pip1 = hash_pip_runtime()
    mudou = [k for k in amb0 if amb0[k] != amb1[k]]
    etapas.append({"nome": "ambiente", "ok": not mudou, "novos": len(mudou),
                   "detalhe_curto": "; ".join(f"{k} {amb0[k]} -> {amb1[k]}" for k in amb0)})
    pip_ok = pip0 == pip1 and not pip0.startswith("erro")
    etapas.append({"nome": "venv_runtime", "ok": pip_ok, "novos": 0 if pip_ok else 1,
                   "detalhe_curto": f"pip freeze sha256 {pip0} igual antes e depois" if pip_ok
                   else f"pip freeze sha256 antes {pip0} depois {pip1}"})
    if fim_wt:
        etapas.append(fim_wt)
    ok = all(e["ok"] for e in etapas)
    resumo = {"ok": ok, "etapas": etapas, "duracao_s": round(time.time() - t0, 1), "commit": id_commit,
              "conhecidos": conhecidos,
              "marco_aprovado": ok and not any(c.get("decisao_talis") == "pendente" for c in conhecidos)}
    json.dump(resumo, open(os.path.join(destino, "RESUMO.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return resumo


def linha_resumo(r: dict) -> str:
    def extra(e):
        if e["nome"] in ("ruff", "basedpyright"):
            return f" ({e['novos']} novos)"
        if e["nome"] == "propriedades":
            return f" ({e['novos']} novos)"
        return f" ({e['detalhe_curto'][:60]})" if e["nome"].startswith("suite:") else ""
    partes = [f"{e['nome']} {'ok' if e['ok'] else 'FALHOU'}{extra(e)}" for e in r["etapas"]]
    pend = sum(c.get("decisao_talis") == "pendente" for c in r["conhecidos"])
    return (f"bateria {'OK' if r['ok'] else 'FALHOU'} · commit {r['commit']} · {r['duracao_s']} s · " + " · ".join(partes)
            + f" · conhecidos {len(r['conhecidos'])} ({pend} pendentes)"
            + f" · marco {'APROVADO' if r['marco_aprovado'] else 'não aprovado'}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "bateria").splitlines()[0])
    ap.add_argument("--commit", default="HEAD")
    ap.add_argument("--pasta")
    ap.add_argument("--saida")
    ap.add_argument("--gerar-base")
    a = ap.parse_args(argv)
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")  # o resumo tem acentos; no terminal do Windows saía "�"
    if a.gerar_base:
        b = gerar_base(a.gerar_base)
        json.dump(b, open(BASE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"base: ruff {sum(b['ruff'].values())}, basedpyright {sum(b['basedpyright'].values())} -> {BASE}")
        return 0
    r = rodar(a.commit, a.pasta, a.saida)
    print(linha_resumo(r))
    print(json.dumps(r, ensure_ascii=False))
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
