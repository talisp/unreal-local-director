"""Controlador de experimentos (v0.0.2, bloco 2): iniciar / rodar / fechar, com estado em disco.

Regras (todas verificadas aqui, nenhuma confiada ao texto do agente):
- experimento só quando a solução é incerta: 2–3 hipóteses ESTRUTURADAS e materialmente diferentes;
  as não escolhidas ficam guardadas (arquivo de alternativas);
- causa comprovada + correção direta = CONSERTO (sem hipóteses), exige evidência existente;
- "aposta" exige meta verificável (métrica, comparador, valor), prazo e critério de encerramento;
- dependências = branches do sandbox que precisam estar INTEGRADAS no master (verificado pelo git);
- cada experimento ganha sua própria cópia de trabalho (git worktree) criada do master: nada de trocar de
  branch nem juntar na mão na pasta compartilhada (06/10: 1,5 h perdida assim);
- no máximo 2 corridas e 60 min por experimento; cada corrida tem no máximo 25 min (teto da ferramenta MCP);
- a corrida só roda script DENTRO da cópia do experimento, com o código do sandbox (que tem a guarda), recusa
  se a guarda.py foi alterada e recusa scripts que apontam para a produção ou para o MCP bruto. O controlador
  não abre caminho novo para fora do sandbox_guard (o terminal do agente continua sendo outro assunto).
- resultado de corrida = código de saída, duração e números lidos da saída (gravados pela ferramenta);
  a interpretação do agente fica separada, marcada como "declarada".
Eventos (iniciado, corrida, recusa, fechado) vão para eventos.jsonl — o bloco 3 consome esse histórico.
"""
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata

from .macros import RAIZ_WORK

SANDBOX = os.environ.get("ULD_SANDBOX", os.path.join(os.path.expanduser("~"), "unreal-macros-sandbox"))
PASTA = os.path.join(RAIZ_WORK, "experimentos")
MAX_CORRIDAS = 2
MAX_MINUTOS = 60
MAX_CORRIDA_S = 1500
GUARDA_REL = "src/unreal_macros/guarda.py"
PROIBIDO_NO_SCRIPT = ("unreal-macros\\src", "unreal-macros/src", "127.0.0.1:8001", "localhost:8001", "_call_cru",
                      "guarda.checar =", "UNREAL_MACROS_TRAVA")
COMPARADORES = (">=", "<=", ">", "<", "==")
LIMIAR_DUPLICATA = 0.5
_STOP = {"a", "o", "as", "os", "de", "da", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas", "um", "uma",
         "para", "por", "com", "que", "se", "ser", "passa", "pelo", "pela", "pelos", "pelas", "ao", "aos", "the", "of",
         "to", "and", "in", "is", "be", "mais", "menos", "como", "sem", "vez"}


class Recusa(ValueError):
    """Pedido recusado pelo controlador (regra violada). A mensagem diz qual regra."""


# ---------- utilidades ----------
def _agora(agora):
    return time.time() if agora is None else agora


def _caminhos(nome: str, pasta: str):
    return os.path.join(pasta, f"{nome}.json"), os.path.join(pasta, nome)


def _evento(pasta: str, ev: dict):
    os.makedirs(pasta, exist_ok=True)
    ev = dict(ev, quando=dt.datetime.now().isoformat(timespec="milliseconds"))
    with open(os.path.join(pasta, "eventos.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def _recusar(pasta: str, nome: str, acao: str, motivo: str):
    _evento(pasta, {"evento": "recusa", "experimento": nome, "acao": acao, "motivo": motivo})
    raise Recusa(motivo)


def _salvar(estado: dict, pasta: str):
    os.makedirs(pasta, exist_ok=True)
    arq, _ = _caminhos(estado["nome"], pasta)
    tmp = arq + ".tmp"
    json.dump(estado, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, arq)


def carregar(nome: str, pasta: str = None) -> dict:
    pasta = pasta or PASTA
    arq, _ = _caminhos(nome, pasta)
    if not os.path.exists(arq):
        raise Recusa(f"experimento '{nome}' não existe")
    return json.load(open(arq, encoding="utf-8"))


def _git(sandbox: str, *args) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", sandbox, *args], capture_output=True, text=True, encoding="utf-8")


def _sha(texto: bytes) -> str:
    return hashlib.sha256(texto).hexdigest()


# ---------- hipóteses ----------
def _radicais(texto: str) -> set:
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return {p[:4] for p in re.findall(r"[a-z0-9_]+", t) if p not in _STOP and len(p) > 1}


def similaridade(h1: dict, h2: dict) -> float:
    """Jaccard dos radicais (4 letras, sem acento e sem palavras vazias) de descrição + mudança. Heurística
    determinística: pega reformulações com as mesmas palavras; paráfrases com vocabulário todo diferente
    escapam (limitação declarada, por isso cada hipótese também precisa de 'mudanca' e 'previsao' próprias)."""
    a = _radicais(h1["descricao"] + " " + h1["mudanca"])
    b = _radicais(h2["descricao"] + " " + h2["mudanca"])
    return len(a & b) / len(a | b) if a | b else 1.0


def _validar_aposta(ap: dict) -> str | None:
    if not isinstance(ap, dict):
        return "aposta precisa ser um objeto com meta, prazo e critério"
    meta = ap.get("meta") or {}
    if not (meta.get("metrica") and meta.get("comparador") in COMPARADORES and isinstance(meta.get("valor"), (int, float))):
        return "aposta sem meta verificável (precisa de metrica, comparador em >=,<=,>,<,== e valor numérico)"
    if not isinstance(ap.get("prazo_min"), int) or not 1 <= ap["prazo_min"] <= MAX_MINUTOS:
        return f"aposta sem prazo válido (prazo_min inteiro de 1 a {MAX_MINUTOS})"
    if len(str(ap.get("criterio_encerramento", "")).strip()) < 10:
        return "aposta sem critério de encerramento"
    return None


def _validar_hipoteses(hips) -> str | None:
    if not isinstance(hips, list) or not 2 <= len(hips) <= 3:
        return "experimento exige 2 ou 3 hipóteses (solução incerta); se a causa já está comprovada, use tipo=conserto"
    for i, h in enumerate(hips):
        if not isinstance(h, dict):
            return f"hipótese {i} precisa ser objeto {{descricao, mudanca, previsao}}"
        for campo, minimo in (("descricao", 10), ("mudanca", 10), ("previsao", 5)):
            if len(str(h.get(campo, "")).strip()) < minimo:
                return f"hipótese {i}: campo '{campo}' vazio ou curto demais"
        if "aposta" in h:
            erro = _validar_aposta(h["aposta"])
            if erro:
                return f"hipótese {i}: {erro}"
    for i in range(len(hips)):
        for j in range(i + 1, len(hips)):
            s = similaridade(hips[i], hips[j])
            if s >= LIMIAR_DUPLICATA:
                return f"hipóteses {i} e {j} são a mesma ideia reformulada (similaridade {s:.2f} >= {LIMIAR_DUPLICATA})"
    return None


# ---------- iniciar / rodar / fechar ----------
def iniciar(nome: str, tipo: str, objetivo: str, hipoteses=None, escolhida: int = 0, dependencias=(),
            causa_evidencia: str = "", correcao: str = "", sandbox: str = None, pasta: str = None, agora=None,
            pedido: str = "") -> dict:
    sandbox, pasta = sandbox or SANDBOX, pasta or PASTA
    from .macros import pausa_ativa
    if pausa_ativa():
        _recusar(pasta, nome or "?", "iniciar", f"PAUSADO pelo supervisor: {pausa_ativa().get('motivo')}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,39}", nome or ""):
        raise Recusa("nome inválido (3–40 caracteres: minúsculas, números e hífen)")
    arq, _ = _caminhos(nome, pasta)
    if os.path.exists(arq):
        _recusar(pasta, nome, "iniciar", "já existe um experimento com esse nome")
    if tipo not in ("experimento", "conserto"):
        _recusar(pasta, nome, "iniciar", "tipo deve ser 'experimento' (solução incerta) ou 'conserto' (causa comprovada)")
    if len(str(objetivo).strip()) < 10:
        _recusar(pasta, nome, "iniciar", "objetivo vazio ou curto demais")
    if pedido:
        from . import direcao
        if pedido != direcao.TRANSVERSAL and pedido not in direcao.ids_pedidos():
            _recusar(pasta, nome, "iniciar", f"pedido '{pedido}' não existe no banco (use um id ou '{direcao.TRANSVERSAL}')")
    limite = MAX_MINUTOS
    if tipo == "conserto":
        if hipoteses:
            _recusar(pasta, nome, "iniciar", "conserto não leva hipóteses: a causa já está comprovada")
        if len(str(correcao).strip()) < 15:
            _recusar(pasta, nome, "iniciar", "conserto exige a correção direta descrita")
        if not _evidencia_existe(causa_evidencia, sandbox):
            _recusar(pasta, nome, "iniciar", "conserto exige evidência existente da causa (relatorio_id ou arquivo do sandbox)")
        alternativas = []
    else:
        erro = _validar_hipoteses(hipoteses)
        if erro:
            _recusar(pasta, nome, "iniciar", erro)
        if not isinstance(escolhida, int) or not 0 <= escolhida < len(hipoteses):
            _recusar(pasta, nome, "iniciar", "índice 'escolhida' inválido")
        ap = hipoteses[escolhida].get("aposta")
        if ap:
            limite = min(limite, ap["prazo_min"])
        alternativas = [dict(h, indice=i) for i, h in enumerate(hipoteses) if i != escolhida]
    for dep in dependencias or ():
        if _git(sandbox, "rev-parse", "--verify", "--quiet", dep).returncode:
            _recusar(pasta, nome, "iniciar", f"dependência '{dep}' não existe no sandbox")
        if _git(sandbox, "merge-base", "--is-ancestor", dep, "master").returncode:
            _recusar(pasta, nome, "iniciar", f"dependência '{dep}' ainda NÃO está integrada no master: peça a integração "
                                             "(registre a dependência) em vez de juntar na mão")
    guarda = _git(sandbox, "show", f"master:{GUARDA_REL}")
    if guarda.returncode:
        _recusar(pasta, nome, "iniciar", "sandbox sem guarda.py no master: recuso experimentar sem guarda")
    branch, worktree = f"exp/{nome}", os.path.join(f"{sandbox}-exp", nome)
    r = _git(sandbox, "worktree", "add", "-b", branch, worktree, "master")
    if r.returncode:
        _recusar(pasta, nome, "iniciar", f"não consegui criar a cópia do experimento: {r.stderr.strip()[:200]}")
    estado = {"nome": nome, "tipo": tipo, "objetivo": objetivo, "hipoteses": hipoteses or [], "escolhida": escolhida,
              "alternativas": alternativas, "dependencias": list(dependencias or ()), "causa_evidencia": causa_evidencia,
              "correcao": correcao, "pedido": pedido or "nao_declarado", "inicio": _agora(agora), "limite_min": limite, "corridas": [], "estado": "aberto",
              "branch": branch, "worktree": worktree, "sandbox": sandbox,
              "guarda_sha": _sha(guarda.stdout.encode("utf-8"))}
    _salvar(estado, pasta)
    for alt in alternativas:  # arquivo de alternativas: nada se perde
        with open(os.path.join(pasta, "alternativas.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"experimento": nome, "situacao": "nao_testada", **alt}, ensure_ascii=False) + "\n")
    _evento(pasta, {"evento": "iniciado", "experimento": nome, "tipo": tipo, "limite_min": limite,
                    "dependencias": estado["dependencias"], "worktree": worktree})
    return estado


def _evidencia_existe(ev: str, sandbox: str) -> bool:
    if not ev:
        return False
    from . import diario
    try:
        diario.carregar_relatorio(ev)
        return True
    except (ValueError, FileNotFoundError):
        pass
    alvo = os.path.realpath(os.path.join(sandbox, ev))
    return alvo.startswith(os.path.realpath(sandbox) + os.sep) and os.path.isfile(alvo)


def _checar_script(estado: dict, script: str, pasta: str) -> str:
    nome = estado["nome"]
    wt = os.path.realpath(estado["worktree"])
    alvo = os.path.realpath(os.path.join(wt, script))
    if not alvo.startswith(wt + os.sep) or not alvo.endswith(".py") or not os.path.isfile(alvo):
        _recusar(pasta, nome, "rodar", f"script fora da cópia do experimento ou inexistente: {script}")
    try:
        atual = open(os.path.join(wt, GUARDA_REL.replace("/", os.sep)), "rb").read().replace(b"\r\n", b"\n")
    except OSError:
        _recusar(pasta, nome, "rodar", "guarda.py ausente na cópia do experimento")
    if _sha(atual) != estado["guarda_sha"]:
        _recusar(pasta, nome, "rodar", "guarda.py da cópia do experimento foi ALTERADA: recuso rodar")
    corpo = open(alvo, encoding="utf-8", errors="replace").read()
    for proibido in PROIBIDO_NO_SCRIPT:
        if proibido in corpo:
            _recusar(pasta, nome, "rodar", f"script referencia algo proibido ({proibido!r}): só o código do sandbox, com guarda")
    return alvo


def rodar(nome: str, script: str, pasta: str = None, agora=None) -> dict:
    pasta = pasta or PASTA
    estado = carregar(nome, pasta)
    from .macros import pausa_ativa
    if pausa_ativa():
        _recusar(pasta, nome, "rodar", f"PAUSADO pelo supervisor: {pausa_ativa().get('motivo')}")
    if estado["estado"] != "aberto":
        _recusar(pasta, nome, "rodar", f"experimento está '{estado['estado']}'")
    if len(estado["corridas"]) >= MAX_CORRIDAS:
        _recusar(pasta, nome, "rodar", f"limite de {MAX_CORRIDAS} corridas atingido: feche o experimento e registre o resultado")
    gasto = _agora(agora) - estado["inicio"]
    restante = estado["limite_min"] * 60 - gasto
    if restante <= 0:
        _recusar(pasta, nome, "rodar", f"prazo de {estado['limite_min']} min esgotado: feche o experimento")
    alvo = _checar_script(estado, script, pasta)
    wt_src = os.path.join(estado["worktree"], "src")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "UNREAL_MACROS_TRAVA", "ULD_SANDBOX")}
    env.update(PYTHONPATH=wt_src, ULD_EXPERIMENTO=nome, PYTHONIOENCODING="utf-8")
    n = len(estado["corridas"]) + 1
    _, dir_logs = _caminhos(nome, pasta)
    os.makedirs(dir_logs, exist_ok=True)
    log = os.path.join(dir_logs, f"corrida_{n}.log")
    _evento(pasta, {"evento": "corrida_iniciada", "experimento": nome, "n": n,
                    "script": os.path.relpath(alvo, estado["worktree"]), "prazo_s": round(min(restante, MAX_CORRIDA_S))})
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, "-X", "utf8", alvo], cwd=wt_src, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=min(restante, MAX_CORRIDA_S))
        saida, codigo, estourou = p.stdout + p.stderr, p.returncode, False
    except subprocess.TimeoutExpired as e:
        saida = ((e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")) + "\n[TEMPO ESGOTADO]"
        codigo, estourou = None, True
    open(log, "w", encoding="utf-8").write(saida)
    m = re.findall(r"(\d+)/(\d+) testes ok", saida)
    corrida = {"n": n, "script": os.path.relpath(alvo, estado["worktree"]), "codigo_saida": codigo, "estourou_tempo": estourou,
               "segundos": round(time.time() - t0, 1), "testes_ok": [int(m[-1][0]), int(m[-1][1])] if m else None,
               "relatorio_ids": re.findall(r"relatorio_id[=: ]+([0-9A-Za-z_-]{6,80})", saida), "log": log}
    estado["corridas"].append(corrida)
    _salvar(estado, pasta)
    _evento(pasta, {"evento": "corrida", "experimento": nome,
                    **{k: corrida[k] for k in ("n", "script", "codigo_saida", "estourou_tempo", "testes_ok")}})
    return corrida


def fechar(nome: str, interpretacao: str = "", pasta: str = None) -> dict:
    pasta = pasta or PASTA
    estado = carregar(nome, pasta)
    if estado["estado"] != "aberto":
        _recusar(pasta, nome, "fechar", f"experimento já está '{estado['estado']}'")
    if not estado["corridas"]:
        _recusar(pasta, nome, "fechar", "fechar exige ao menos 1 corrida (o resultado vem da ferramenta, não de texto)")
    ult = estado["corridas"][-1]
    estado["resultado"] = {"corridas": len(estado["corridas"]), "ultima_codigo_saida": ult["codigo_saida"],
                           "ultima_testes_ok": ult["testes_ok"], "estourou_tempo": any(c["estourou_tempo"] for c in estado["corridas"])}
    estado["interpretacao_declarada"] = interpretacao
    estado["estado"] = "fechado"
    estado["fechado_em"] = time.time()
    _salvar(estado, pasta)
    _evento(pasta, {"evento": "fechado", "experimento": nome, "resultado": estado["resultado"]})
    return estado


def registrar_escalada(linha: str, motivo: str, pasta: str = None) -> dict:
    """O agente passa a linha para um humano (degrau 'escalar'). Para o supervisor isso é ESPERA humana até a próxima
    tentativa: suspende o relógio de progresso, mas NÃO o renova (escalar não pode virar truque para ganhar tempo)."""
    pasta = pasta or PASTA
    if len(str(motivo).strip()) < 10:
        raise Recusa("escalada exige o motivo (diagnóstico) em uma frase")
    ev = {"evento": "escalada", "experimento": linha, "motivo": motivo}
    _evento(pasta, ev)
    return ev
