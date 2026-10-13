"""Astra 0.2.0: fase A independente em fotografia, fase B local depois do parecer.
Sem --enviar --confirmo-cota e campanha preparada não há inferência.
Modo histórico não certifica execução ou identidade. Veja --help e referências da skill.
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import hashlib
import time
import uuid
from pathlib import Path
from typing import cast

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROTINA = os.path.join(RAIZ, "docs", "rotinas", "L3_ASTRA.md")
HERMES = os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes", "bin", "hermes.cmd")
PACOTE_MAX = 14000  # caracteres do pedido final; excesso bloqueia, sem corte
SECAO_MAX = 4000
GRAVIDADES = ("alta", "media", "baixa")
VERSION = "0.2.0"
PEDIDO_MAX = PACOTE_MAX
ACHADOS_JSON_MAX_BYTES = 64000


def git(*args) -> str:
    r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, timeout=60)
    return r.stdout.decode("utf-8", "replace").rstrip("\r\n") if r.returncode == 0 else ""


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


PROMPT = """Você é Astra, auditor independente do Director. Responda uma pergunta do pacote.
Não edite nada. Não use Unreal, porta 8001 ou drive Y:, rede, outros modelos, macros, processos Runtime, publicação ou testes com efeitos reais.
Leia integralmente docs/TALIS.md na cópia, obedeça as regras neutras de AGENTS.md e inspecione apenas os arquivos autorizados. Se precisar de outro, explique a lacuna sem abri-lo.
Esta é fase A: não recebeu conclusões de investigação anterior. A escolha do escopo pelo organizador pode ser informada; não alegue cegueira absoluta.
Síntese até 600 palavras (prosa + resumo), até cinco prioridades opcionais. Não agrupe defeitos diferentes nem invente cinco para preencher quota. Registro técnico JSON até 64000 bytes, sem máximo de achados distintos sustentados. Não é teto de tokens de raciocínio.
Separe leitura de reprodução e hipótese. Cada item tem achado, gravidade alta|media|baixa, prova canônica arquivo:linha, correcao e verificado booleano (por leitura, não prova de reprodução). Pode adicionar provas com todas as referências.
Termine com UM bloco JSON, sem texto depois:
```json
{"pergunta":"<repita exatamente>","achados":[],"resumo":"<síntese>","prioridades":[]}
```
"""


def _arquivo_autorizado(path):
    _relativo(path)
    partes = path.lower().split("/")
    negados = {"agents.md", "claude.md", ".hermes.md", "handoff.md", "registro.md", "pendencias.md", ".env", "auth.json"}
    if any(x in negados or x.startswith("handoff") or x.startswith(".hermes") for x in partes):
        raise ValueError(f"arquivo com contexto/credencial não autorizado na fase A: {path}")
    if partes[0] in ("work", "escaladas", "ideias", "relatosjunior", "biblioteca"):
        raise ValueError(f"resultado/relato não autorizado na fase A: {path}")
    p = os.path.join(RAIZ, path)
    if not os.path.isfile(p) or not _dentro(RAIZ, p):
        raise ValueError(f"arquivo ausente/externo: {path}")
    return p


def _identidade(arquivos):
    if not arquivos or len(arquivos) > 5 or len(set(arquivos)) != len(arquivos):
        raise ValueError("lista explícita entre 1 e 5 arquivos distintos obrigatória")
    itens = []
    for path in arquivos:
        p = _arquivo_autorizado(path)
        raw = Path(p).read_bytes()
        itens.append({"path": path, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "linhas": _linhas(p)})
    return itens


def _pacote_identidade(pergunta, itens, head, dirty, base):
    if not isinstance(pergunta, str) or not pergunta.strip():
        raise ValueError("pergunta não vazia obrigatória")
    return (f"## A pergunta\n{pergunta}\n## Commit-base\n{head}\nBase de comparação: {base or 'não fornecida'}\n"
            f"Árvore sujo: {'sim' if dirty else 'não'}; a identidade revisada são os hashes, não apenas HEAD.\n"
            "## Arquivos que você pode abrir\n" + "\n".join(f"- {x['path']} | SHA256 {x['sha256']} | {x['linhas']} linhas | {x['bytes']} bytes" for x in itens) +
            "\nRegras obrigatórias: docs/TALIS.md integral e AGENTS.md neutro da cópia.\n")


def montar_pacote(pergunta: str, arquivos: list, base=None, resumo_bateria=None) -> str:
    # resumo_bateria permanece parâmetro de compatibilidade, não entra na fase A.
    return _pacote_identidade(pergunta, _identidade(arquivos), git("rev-parse", "HEAD"), git("status", "--porcelain"), base)


def montar_pedido(pacote: str) -> str:
    pedido = PROMPT + "\n# Pacote\n" + pacote
    if len(pedido) > PEDIDO_MAX:
        raise ValueError(f"pedido final excede {PEDIDO_MAX} caracteres; reduza explicitamente, sem truncar")
    return pedido


# ---------- resposta ----------
def _dentro(raiz, caminho):
    from pathlib import Path
    try:
        Path(caminho).resolve().relative_to(Path(raiz).resolve())
        return True
    except (ValueError, OSError):
        return False


def _relativo(path):
    from pathlib import PurePosixPath
    if not isinstance(path, str) or not path or "\\" in path or ":" in path:
        raise ValueError("caminho relativo não canônico")
    p = PurePosixPath(path)
    if p.is_absolute() or any(x in ("", ".", "..") for x in path.split("/")):
        raise ValueError("caminho relativo não canônico")
    return path


def _hash(path):
    import hashlib
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _linhas(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return sum(1 for _ in f)


def conferir_resposta(texto: str, raiz=None, *, pergunta_esperada=None, permitidos=None, manifesto=None) -> dict:
    raiz = raiz or RAIZ
    estrito = pergunta_esperada is not None or permitidos is not None or manifesto is not None
    r = {"ok": False, "motivos": [], "achados": [], "pergunta": None, "resumo": None,
         "modo": "estrito" if estrito else "historico", "incompleto": not estrito, "validado": False}
    if not isinstance(texto, str):
        r["motivos"].append("resposta tem de ser texto")
        return r
    blocos = list(re.finditer(r"```json\s*(.*?)```", texto, re.S))
    if len(blocos) != 1 or texto[blocos[0].end():].strip():
        r["motivos"].append("sem bloco JSON terminal" if not blocos else "exigir um único bloco JSON terminal")
        return r
    b = blocos[0]
    try:
        d = json.loads(b.group(1))
    except (ValueError, TypeError):
        r["motivos"].append("bloco JSON ilegível")
        return r
    if not isinstance(d, dict):
        r["motivos"].append("JSON tem de ser objeto")
        return r
    for key in ("pergunta", "resumo"):
        if not isinstance(d.get(key), str) or not d[key].strip():
            r["motivos"].append(f"falta '{key}' textual não vazio")
    r["pergunta"], r["resumo"] = d.get("pergunta"), d.get("resumo")
    if pergunta_esperada is not None and d.get("pergunta") != pergunta_esperada:
        r["motivos"].append("pergunta divergente")
    prosa = texto[:b.start()] + texto[b.end():]
    palavras = len(prosa.split()) + len(str(d.get("resumo", "")).split())
    if palavras > 600:
        r["motivos"].append("síntese excede 600 palavras")
    if len(b.group(1).encode("utf-8")) > ACHADOS_JSON_MAX_BYTES:
        r["motivos"].append("registro JSON excede limite de bytes")
    if not isinstance(d.get("achados"), list):
        r["motivos"].append("'achados' tem de ser uma lista")
        return r
    if manifesto:
        permitidos = [x["path"] for x in manifesto["arquivos"]]
        for x in manifesto["arquivos"]:
            p = os.path.join(raiz, x["path"])
            if not os.path.isfile(p) or _hash(p) != x["sha256"]:
                r["motivos"].append(f"snapshot divergiu: {x['path']}")
    permitidos = set(permitidos) if permitidos is not None else None
    for i, a in enumerate(d["achados"], 1):
        motivos = []
        if not isinstance(a, dict):
            r["motivos"].append(f"achado {i}: tipo inválido")
            continue
        for key in ("achado", "correcao"):
            if not isinstance(a.get(key), str) or not a[key].strip():
                motivos.append(f"falta '{key}' textual")
        if a.get("gravidade") not in GRAVIDADES:
            motivos.append("gravidade inválida")
        if type(a.get("verificado")) is not bool:
            motivos.append("'verificado' tem de ser true ou false")
        provas = [a.get("prova")]
        if "provas" in a:
            if not isinstance(a["provas"], list) or not a["provas"]:
                motivos.append("provas tem de ser lista não vazia")
            else:
                provas.extend(a["provas"])
        for prova in provas:
            match = re.fullmatch(r"`?([^`]+):([1-9][0-9]*)`?", prova) if isinstance(prova, str) else None
            if not match:
                motivos.append("prova sem arquivo:linha válida")
                continue
            path, linha = match.group(1), int(match.group(2))
            try:
                _relativo(path)
            except ValueError:
                motivos.append("prova com caminho não autorizado")
                continue
            arq = os.path.join(raiz, path)
            if not _dentro(raiz, arq) or (permitidos is not None and path not in permitidos):
                motivos.append("prova fora da lista/raiz autorizada")
            elif not os.path.isfile(arq):
                motivos.append("prova aponta arquivo inexistente")
            elif linha > _linhas(arq):
                motivos.append("prova aponta linha inexistente")
        r["achados"].append({"n": i, "achado": a.get("achado"), "gravidade": a.get("gravidade"),
                             "prova": a.get("prova"), "ok": not motivos, "motivos": motivos})
        r["motivos"].extend(f"achado {i}: {m}" for m in motivos)
    priorities = d.get("prioridades", [])
    if (not isinstance(priorities, list) or len(priorities) > 5 or
            any(type(x) is not int or x < 1 or x > len(d["achados"]) for x in priorities) or
            len(set(priorities)) != len(priorities)):
        r["motivos"].append("prioridades inválidas")
    r["ok"] = not r["motivos"]
    return r


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
    os.makedirs(os.path.join(RAIZ, "escaladas"), exist_ok=True)
    with open(os.path.join(RAIZ, rel), "x", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(linhas) + "\n")
    return rel


def _json_novo(path, data):
    with open(path, "x", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _evento(pasta, estado_novo, **data):
    base = Path(pasta) / "eventos"
    base.mkdir(exist_ok=True)
    payload = dict(data, estado=estado_novo, horario=dt.datetime.now(dt.timezone.utc).isoformat())
    for _ in range(100):
        n = max([int(p.stem) for p in base.glob("*.json")] + [0]) + 1
        try:
            _json_novo(base / f"{n:04d}.json", dict(payload, n=n))
            return n
        except FileExistsError:
            continue
    raise ValueError("disputa persistente ao reservar evento")


def eventos(pasta):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((Path(pasta) / "eventos").glob("*.json"))]


def estado(pasta):
    es = eventos(pasta)
    return es[-1]["estado"] if es else "DESCONHECIDO"


def carregar_manifesto(pasta):
    path = Path(pasta)
    man = json.loads((path / "manifesto.json").read_text(encoding="utf-8"))
    esperado = (path / "manifesto.sha256").read_text(encoding="ascii").strip()
    if man.get("schema_version") != 1 or _hash(path / "manifesto.json") != esperado:
        raise ValueError("manifesto incompatível/divergente")
    return man


def preparar(tema, pergunta, arquivos, base=None, *, copias_base=None, modelo="gpt-6-astra", gerar_sufixo=None):
    if not isinstance(modelo, str) or not modelo.strip():
        raise ValueError("modelo explícito obrigatório")
    itens = _identidade(arquivos)
    head = git("rev-parse", "HEAD")
    if not re.fullmatch("[0-9a-f]{40}", head):
        raise ValueError("HEAD completo não identificado")
    if base and (not re.fullmatch("[0-9a-f]{7,40}", base) or not git("rev-parse", "--verify", base + "^{commit}")):
        raise ValueError("commit-base inválido/não disponível")
    status = git("status", "--porcelain")
    pedido = montar_pedido(_pacote_identidade(pergunta, itens, head, status, base))
    talis = Path(RAIZ) / "docs/TALIS.md"
    ordens = talis.read_bytes()  # obrigatório, integral, não sanitizar
    neutro = ("# Auditoria independente — somente leitura\nLeia docs/TALIS.md inteiro e cumpra suas ordens. "
              "Segurança: não editar, publicar, abrir Unreal/8001/Y:, iniciar Runtime/outros modelos, usar rede ou ler credenciais. "
              "Leia somente código/contratos autorizados e as regras desta cópia. Não atualizar documentos globais. "
              "Solicite lacuna de contrato antes de abrir outro arquivo. A lista não é sandbox de leitura.\n")
    if copias_base is None:
        home = os.environ.get("HERMES_HOME")
        if not home:
            raise ValueError("HERMES_HOME/scratch explícito obrigatório")
        copias_base = str(Path(home) / "cache/scratch/astra-a")
    if _dentro(RAIZ, copias_base):
        raise ValueError("cópia independente deve ficar fora da árvore do repositório")
    prefixo = re.sub(r"[^a-z0-9]+", "-", str(tema).lower()).strip("-")[:60] or "auditoria"
    parent = Path(RAIZ) / "work/astra"
    parent.mkdir(parents=True, exist_ok=True)
    pasta = None
    for _ in range(10):
        suffix = (gerar_sufixo or (lambda: uuid.uuid4().hex[:12]))()
        if not re.fullmatch("[A-Za-z0-9_-]+", suffix):
            raise ValueError("sufixo inseguro")
        candidate = parent / (prefixo + "-" + suffix)
        try:
            candidate.mkdir(exist_ok=False)
            pasta = candidate
            break
        except FileExistsError:
            continue
    if pasta is None:
        raise ValueError("não foi possível reservar campanha exclusiva")
    copia = Path(copias_base) / pasta.name
    copia.parent.mkdir(parents=True, exist_ok=True)
    copia.mkdir(exist_ok=False)
    for item in itens:
        dest = copia / item["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        raw = (Path(RAIZ) / item["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("arquivo mudou durante preparação; fotografia não concluída")
        with dest.open("xb") as f:
            f.write(raw)
    (copia / "docs").mkdir(exist_ok=True)
    (copia / "docs/TALIS.md").write_bytes(ordens)
    (copia / "AGENTS.md").write_text(neutro, encoding="utf-8")
    with (pasta / "pedido.md").open("x", encoding="utf-8", newline="\n") as f:
        f.write(pedido)
    man = {"schema_version": 1, "instrument_version": VERSION, "skill_version": "0.2.0",
           "head": head, "base": base, "dirty": bool(status), "dirty_arquivos": [x[3:] for x in status.splitlines()],
           "arquivos": itens, "pergunta": pergunta, "modelo": modelo, "copia": str(copia),
           "pedido_sha256": _hash(pasta / "pedido.md"), "pedido_chars": len(pedido),
           "escopo": "Seleção do organizador pode ser informada. Sem conclusões anteriores; não alega cegueira absoluta.",
           "regras": [{"path": "docs/TALIS.md", "sha256": _hash(copia / "docs/TALIS.md")},
                       {"path": "AGENTS.md", "sha256": _hash(copia / "AGENTS.md")}],
           "python": sys.version.split()[0], "instrument_sha256": _hash(__file__)}
    source_skill = Path(RAIZ) / "docs/skills/astra.md"
    man["skill_sha256"] = _hash(source_skill) if source_skill.is_file() else None
    _json_novo(pasta / "manifesto.json", man)
    with (pasta / "manifesto.sha256").open("x", encoding="ascii") as f:
        f.write(_hash(pasta / "manifesto.json"))
    _evento(pasta, "PREPARADO")
    return str(pasta)


def _validar_campanha(pasta, man):
    if _hash(Path(pasta) / "pedido.md") != man["pedido_sha256"]:
        raise ValueError("pedido alterado desde aprovação/preparo")
    texto = (Path(pasta) / "pedido.md").read_text(encoding="utf-8")
    if len(texto) > PEDIDO_MAX or len(texto) != man["pedido_chars"]:
        raise ValueError("tamanho do pedido divergente")
    for item in man["arquivos"] + man["regras"]:
        p = Path(man["copia"]) / item["path"]
        if not _dentro(man["copia"], p) or not p.is_file() or _hash(p) != item["sha256"]:
            raise ValueError("snapshot/regras divergentes: " + item["path"])


def _vivo(pid):
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.windll.kernel32
            kernel.OpenProcess.restype = wintypes.HANDLE
            kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
            kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
            h = kernel.OpenProcess(0x100000, False, pid)
            if not h:
                return False
            res = kernel.WaitForSingleObject(h, 0)
            kernel.CloseHandle(h)
            return res == 258
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _matar_pid(pid):
    # Só o PID criado/registrado pela execução, nunca processos encontrados por nome.
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=30)
    else:
        import signal
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def _login_ok():
    r = subprocess.run(["codex", "login", "status"], capture_output=True, timeout=60, shell=os.name == "nt")
    return r.returncode == 0 and b"Logged in" in r.stdout + r.stderr


def enviar(pasta, *, confirmo_cota=False, popen=None, login_ok=None, comando=None, timeout_s=1800, matar=None):
    # O filho muda de cwd para a fotografia: fixar o caminho absoluto ANTES.
    # abspath preserva o nome curto do Windows; resolve() o trocava e quebrava a comparação por texto.
    pasta = Path(os.path.abspath(pasta))
    if not confirmo_cota:
        return {"codigo": 2, "estado": estado(pasta), "motivo": "precisa autorização específica e confirmação"}
    if estado(pasta) != "PREPARADO":
        return {"codigo": 3, "estado": estado(pasta), "motivo": "não reenviar campanha iniciada"}
    man = carregar_manifesto(pasta)
    try:
        _validar_campanha(pasta, man)
    except (ValueError, OSError) as e:
        return {"codigo": 3, "estado": estado(pasta), "motivo": str(e)}
    if any((Path(pasta) / p).exists() for p in ("resposta.md", "log.txt", "parecer-A.md", "envio.lock")):
        return {"codigo": 3, "estado": estado(pasta), "motivo": "artefato anterior presente"}
    if not (login_ok or _login_ok)():
        return {"codigo": 3, "estado": estado(pasta), "motivo": "login não confirmado"}
    try:
        with (Path(pasta) / "envio.lock").open("x", encoding="utf-8") as f:
            f.write(man["pedido_sha256"])
    except FileExistsError:
        return {"codigo": 3, "estado": estado(pasta), "motivo": "execução já reservada"}
    _validar_campanha(pasta, man)
    _evento(pasta, "EXECUTANDO", modelo_solicitado=man["modelo"])
    cmd = list(comando or ["codex"]) + ["exec", "-m", man["modelo"], "-s", "read-only", "-C", man["copia"],
                                      "--skip-git-repo-check", "-o", str(Path(pasta) / "resposta.md"), "-"]
    t0 = time.monotonic()
    proc = None
    try:
        with (Path(pasta) / "log.txt").open("xb") as log:
            kwargs = {"stdin": subprocess.PIPE, "stdout": log, "stderr": log,
                      "cwd": man["copia"], "env": dict(os.environ, UNREAL_MACROS_OFFLINE="1")}
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            else:
                kwargs["start_new_session"] = True
            proc = cast(subprocess.Popen[bytes], (popen or subprocess.Popen)(cmd, text=False, **kwargs))
            proc.communicate(input=(Path(pasta) / "pedido.md").read_bytes(), timeout=timeout_s)
    except (subprocess.TimeoutExpired, KeyboardInterrupt) as interrupcao:
        _evento(pasta, "INTERROMPIDO", duracao_s=time.monotonic()-t0, codigo=None)
        if proc:
            (matar or (lambda p: _matar_pid(p.pid)))(proc)
            try:
                proc.communicate(timeout=10)
            except (subprocess.TimeoutExpired, KeyboardInterrupt, ValueError):
                proc.kill()
        if isinstance(interrupcao, KeyboardInterrupt):
            raise interrupcao
        return {"codigo": 3, "estado": "INTERROMPIDO"}
    except OSError as e:
        _evento(pasta, "FALHOU", motivo=str(e), duracao_s=time.monotonic()-t0)
        return {"codigo": 3, "estado": "FALHOU"}
    logtext = (Path(pasta) / "log.txt").read_text(encoding="utf-8", errors="replace")
    models = re.findall(r"(?m)^model:\s*(\S+)", logtext)
    observado = models[-1] if models else "desconhecido"
    dados = {"modelo_solicitado": man["modelo"], "modelo_observado": observado,
             "duracao_s": time.monotonic()-t0, "codigo": proc.returncode, "log_sha256": _hash(Path(pasta)/"log.txt")}
    resposta = Path(pasta) / "resposta.md"
    if proc.returncode != 0 or not resposta.is_file() or (models and observado != man["modelo"]):
        _evento(pasta, "FALHOU", **dados)
        return {"codigo": 3, "estado": "FALHOU"}
    _validar_campanha(pasta, man)
    texto = resposta.read_text(encoding="utf-8")
    conf = conferir_resposta(texto, man["copia"], manifesto=man, pergunta_esperada=man["pergunta"])
    _json_novo(Path(pasta) / "conferencia-A.json", conf)
    if not conf["ok"]:
        _evento(pasta, "FALHOU", motivos=conf["motivos"], **dados)
        return {"codigo": 3, "estado": "FALHOU"}
    with (Path(pasta) / "parecer-A.md").open("xb") as f:
        f.write(resposta.read_bytes())
    _evento(pasta, "PARECER_SALVO", parecer_sha256=_hash(Path(pasta)/"parecer-A.md"), **dados)
    return {"codigo": 0, "estado": "PARECER_SALVO"}


def conferir_campanha(pasta):
    man = carregar_manifesto(pasta)
    _validar_campanha(pasta, man)
    finais = [e for e in eventos(pasta) if e["estado"] == "PARECER_SALVO"]
    if not finais or _hash(Path(pasta)/"parecer-A.md") != finais[-1]["parecer_sha256"]:
        raise ValueError("parecer A ausente/divergente")
    return conferir_resposta((Path(pasta)/"parecer-A.md").read_text(encoding="utf-8"), man["copia"],
                             manifesto=man, pergunta_esperada=man["pergunta"])


def retomar(pasta):
    carregar_manifesto(pasta)
    st = estado(pasta)
    ambiguo = st == "EXECUTANDO"
    if ambiguo:
        _evento(pasta, "INTERROMPIDO", motivo="estado ambíguo; não comprova término nem processo morto")
        st = "INTERROMPIDO"
    return {"estado": st, "ambiguo": ambiguo, "reenviar": False,
            "proximo": "conferir artefatos existentes; nenhuma nova inferência automática"}


def _ler_relatorio(path):
    return Path(path).read_text(encoding="utf-8")


def comparar_campanha(pasta, relatorios):
    if estado(pasta) != "PARECER_SALVO":
        raise ValueError("comparar somente depois do parecer A salvo; não repetir comparação em mesmo destino")
    conf = conferir_campanha(pasta)
    if not conf["ok"]:
        raise ValueError("parecer incompatível")
    a = {i["prova"] for i in conf["achados"]}
    q, fontes = set(), []
    for path in relatorios:
        txt = _ler_relatorio(path)
        q.update(re.findall(r"[A-Za-z0-9_./-]+\.[A-Za-z0-9]+:[1-9][0-9]*", txt))
        fontes.append({"path": str(path), "sha256": _hash(path)})
    r = {"em_ambos": sorted(a & q), "so_a": sorted(a-q), "so_qwen": sorted(q-a), "relatorios": fontes,
         "limite": "cruzamento de referências, não comparação de causas/verdade; interpretação local pendente"}
    _json_novo(Path(pasta)/"comparacao.json", r)
    _evento(pasta, "COMPARADO", comparacao_sha256=_hash(Path(pasta)/"comparacao.json"))
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(description="Astra 0.2.0: prepara A independente; compara localmente após parecer")
    ap.add_argument("--tema")
    ap.add_argument("--pergunta", default="")
    ap.add_argument("--arquivos", default="")
    ap.add_argument("--base")
    ap.add_argument("--modelo", default="gpt-6-astra")
    ap.add_argument("--fase", choices=("preparar", "enviar", "conferir", "retomar", "comparar"), default="preparar")
    ap.add_argument("--campanha")
    ap.add_argument("--enviar", action="store_true")
    ap.add_argument("--confirmo-cota", action="store_true")
    ap.add_argument("--conferir")
    ap.add_argument("--relatorios", nargs="*")
    a = ap.parse_args(argv)
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")
    try:
        if a.enviar or a.fase == "enviar":
            if not a.enviar or not a.confirmo_cota or not a.campanha:
                print("envio exige campanha preparada, --enviar e --confirmo-cota; autorização específica humana")
                return 2
            res = enviar(a.campanha, confirmo_cota=True)
            print(json.dumps(res, ensure_ascii=False))
            return res["codigo"]
        if a.conferir:
            conf = conferir_resposta(Path(a.conferir).read_text(encoding="utf-8"))
            rel = gravar_escalada(a.tema or "historico", a.pergunta or conf.get("pergunta") or "", "historico-nao-identificado",
                                  Path(a.conferir).read_text(encoding="utf-8"), conf)
            print("conferência histórica incompleta", rel)
            return 0 if conf["ok"] else 1
        if a.fase != "preparar":
            if not a.campanha:
                return 2
            func = {"conferir": conferir_campanha, "retomar": retomar, "comparar": comparar_campanha}[a.fase]
            res = func(a.campanha, a.relatorios or []) if a.fase == "comparar" else func(a.campanha)
            print(json.dumps(res, ensure_ascii=False))
            return 1 if res.get("ok") is False else 0
        if not a.tema or not a.arquivos:
            print("preparação exige tema, pergunta e lista explícita; não gastar por porta legada")
            return 2
        pasta = preparar(a.tema, a.pergunta, a.arquivos.split(","), a.base, modelo=a.modelo)
        print("Astra preparado sem inferência:", pasta)
        return 0
    except (ValueError, OSError) as e:
        print("Astra bloqueado:", str(e))
        return 2


if __name__ == "__main__":
    sys.exit(main())
