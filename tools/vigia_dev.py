"""Vigia do hermes-dev (07/10): acompanha uma rodada longa do Qwen, destrava o que é seguro e, quando ele para,
relança com o prompt corrigido. Python determinístico; o juízo, quando precisa, é do próprio Qwen (crítico de olhos
frescos, outra sessão). O Claude não fica no laço.

Lê: o agent.log do perfil hermes-dev (só as sessões que vigia), os arquivos da rodada (tentativas.jsonl,
FECHAMENTO.md), a trava, a porta do Unreal e o modelo. Reaproveita: o empurrão com limite das vigias de 06/10
(src/vigia_hermes.py, tools/vigia_v003.py), o diagnóstico de trava de src/unreal_macros/trava.py e o PAUSA do
supervisor. Diferenças: relança sempre numa sessão NOVA pela linha de comando (a CLI recusa retomar conversa aberta
no Desktop: SESSION_NOT_OWNED), com --max-turns e --run-budget; aplica a regra de dois; tem tetos por hora e noite.

Nunca: mexe no Unreal, salva, usa o MCP bruto, mexe em perfil do Hermes ou no Runtime, assume trava de dono vivo,
apaga dados, chama Claude/Codex, publica.

Uso (na raiz do repositório, Python do venv):
  ligar:     python tools/vigia_dev.py --rodada work\\fila_2026-10-07 --pedido escaladas\\2026-10-07-RODADA-fila-de-movimentos.md --ate 08:00
  só olhar:  ... --uma-vez --seco      (uma checagem, mostra a decisão, não age)
  pausar:    criar work\\vigia\\PAUSA   (continua olhando e registrando, não age; apagar para voltar)
  desligar:  criar work\\vigia\\PARAR   (ou Ctrl+C)
  resumo:    python tools/vigia_dev.py --resumo   (escreve work\\vigia\\RESUMO.md)
"""
import argparse
import datetime as dt
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
from unreal_macros import trava as T  # noqa: E402  # pyright: ignore[reportMissingImports]

PASTA = os.path.join(RAIZ, "work", "vigia")
TRAVA = os.environ.get("UNREAL_MACROS_TRAVA", os.path.join(RAIZ, "work", "unreal.trava"))
HERMES_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes")
HERMES_CMD = os.path.join(HERMES_DIR, "bin", "hermes.cmd")
PERFIL = "hermes-dev"  # --perfil troca (ex.: codex-unreal-economico, o Runtime/Productor)
LOG_DEV = os.path.join(HERMES_DIR, "profiles", PERFIL, "logs", "agent.log")
MODELO = "http://127.0.0.1:8080/v1/models"
PREFIXO = "[vigia do hermes-dev]"  # só nas sessões de TRABALHO relançadas (a vigia passa a acompanhá-las)
PREFIXO_CRITICO = "[critico da vigia]"  # sessões do crítico: nunca entram na lista vigiada

LIM: dict[str, float] = {"intervalo_s": 300, "ocioso_min": 10, "silencio_caiu_min": 30, "sem_progresso_min": 60, "critica_cada_min": 30,
       "relancos_hora": 3, "relancos_noite": 10, "espera_relanco_min": 15, "max_turns": 200, "run_budget_s": 5400}

CONSELHO = {
    "limite": "Você usou todas as chamadas de ferramenta de um turno. Trabalhe em blocos menores: uma tentativa "
              "completa (montar, avaliar, registrar) por vez, e registre antes de começar a próxima.",
    "falou_e_parou": "Você encerrou o turno respondendo em texto, mas a rodada não terminou (não há FECHAMENTO.md). "
                     "Ninguém vai responder durante a noite: se estava esperando uma resposta, decida sozinho pela "
                     "regra do pedido. Se acha que terminou, escreva o FECHAMENTO.md.",
    "interrompido": "A sessão anterior foi interrompida no meio. Antes da próxima tentativa, confira a trava e a cena "
                    "(contagem de atores igual à do início; só os seus TESTE_FILA_*).",
    "caiu": "A sessão anterior parou de responder (sem atividade por muito tempo). Antes da próxima tentativa, confira "
            "a trava e a cena (contagem de atores igual à do início; só os seus TESTE_FILA_*).",
    "orcamento": "Acabou o tempo da sessão anterior (é normal: cada sessão tem um teto). Continue de onde parou.",
    "estado_parcial": "A última linha do registro é estado_parcial: limpe só os seus TESTE_FILA_*, confira a contagem "
                      "de atores e registre o resultado antes de qualquer tentativa nova.",
}
MUDAR = ("Esta é a SEGUNDA vez seguida que você para pelo mesmo motivo sem progresso entre as duas. Não repita o "
         "mesmo caminho: feche a linhagem atual (linha linhagem_fechada com o motivo) e abra outra a partir de um "
         "ponto diferente, ou mude a forma de trabalhar que causou a parada.")


# ---------- leitura (sem efeito colateral) ----------
_RE_LINHA = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ \w+ (?:\[(\w+)\] )?(.*)$")


def _ts(s: str) -> float:
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").timestamp()


def ler_log(linhas: list, sessoes: set) -> dict:
    """Do agent.log, só das sessões vigiadas. Revisão em segundo plano (turno 'Review the conve...') não conta."""
    o = {"ultima_atividade": 0.0, "inicio_turno": 0.0, "fim_turno": 0.0, "motivo_fim": None, "contexto_in": None,
         "sessao": None, "novas": []}
    revisao = {}
    for ln in linhas:
        m = _RE_LINHA.match(ln.rstrip("\n"))
        if not m:
            continue
        quando, sid, txt = _ts(m.group(1)), m.group(2), m.group(3)
        if "conversation turn:" in txt and f"msg='{PREFIXO}" in txt and sid and sid not in sessoes:
            o["novas"].append(sid)  # sessão que a própria vigia lançou
            sessoes = sessoes | {sid}
        if not sid or sid not in sessoes:
            continue
        if "conversation turn:" in txt:
            revisao[sid] = "msg='Review the conve" in txt or "origin=background_review" in txt
            if not revisao[sid]:
                o["inicio_turno"], o["sessao"] = quando, sid
            continue
        if revisao.get(sid):
            if "Turn ended:" in txt:
                revisao[sid] = False
            continue
        if "Turn ended:" in txt:
            r = re.search(r"reason=([a-z_]+)", txt)
            o["fim_turno"], o["motivo_fim"], o["sessao"] = quando, r.group(1) if r else "?", sid
        elif "API call #" in txt or "tool " in txt:
            o["ultima_atividade"], o["sessao"] = quando, sid
            c = re.search(r" in=(\d+)", txt)
            if c:
                o["contexto_in"] = int(c.group(1))
    o["turno_ativo"] = o["inicio_turno"] > o["fim_turno"]
    return o


def ler_rodada(pasta: str) -> dict:
    tent, especiais, ultimo_especial = [], [], None
    arq = os.path.join(pasta, "tentativas.jsonl")
    if os.path.exists(arq):
        for ln in open(arq, encoding="utf-8", errors="replace"):
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            tl = d.get("tipo_linha")
            if tl == "tentativa" or (tl is None and d.get("tipo") in ("ajuste", "exploracao")):
                tent.append(d)
                ultimo_especial = "estado_parcial" if d.get("classe_erro") == "estado_parcial" else None
            elif tl not in ("tentativa_inicio",):
                especiais.append(tl or d.get("tipo"))
                ultimo_especial = tl or d.get("tipo")
    notas = [t["nota"] for t in tent if isinstance(t.get("nota"), (int, float))]
    try:
        pendente = json.load(open(os.path.join(pasta, "estado.json"), encoding="utf-8")).get("pendente")
    except (OSError, ValueError):
        pendente = None
    return {"tentativas": len(tent), "melhor_nota": min(notas) if notas else None,
            "ultimas": [{k: t.get(k) for k in ("n", "linhagem", "tipo", "nota", "classe_erro", "aprendizado")} for t in tent[-3:]],
            "terminou": os.path.exists(os.path.join(pasta, "FECHAMENTO.md")) or "fechamento" in especiais
            or os.path.exists(os.path.join(pasta, "ENSAIO.md")),  # o ensaio fecha com ENSAIO.md: não relançar depois
            "ultimo_especial": ultimo_especial, "linhagens_fechadas": especiais.count("linhagem_fechada"),
            "pendente": pendente}


def saude() -> dict:
    s = {}
    try:
        urllib.request.urlopen(MODELO, timeout=10).read(100)
        s["modelo"] = True
    except urllib.error.HTTPError:
        s["modelo"] = True  # respondeu (401 sem chave): está no ar; só falha de conexão conta como fora
    except Exception:  # noqa: BLE001
        s["modelo"] = False
    try:
        socket.create_connection(("127.0.0.1", 8001), timeout=3).close()
        s["unreal"] = True
    except OSError:
        s["unreal"] = False
    st = T.estado(TRAVA)
    s["trava"], s["trava_motivo"] = st["estado"], st["motivo"]
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*fila_2026*' -or $_.CommandLine -like '*\\work\\fila*' }).Count"],
                           capture_output=True, text=True, timeout=30)
        s["scripts_da_rodada"] = int((r.stdout or "0").strip() or 0)
    except Exception:  # noqa: BLE001
        s["scripts_da_rodada"] = None
    return s


# ---------- decisão (pura: testável sem Hermes nem Unreal) ----------
def _causa(motivo: str | None) -> str:
    m = motivo or ""
    if m.startswith("max_iterations"):
        return "limite"
    if m.startswith("text_response"):
        return "falou_e_parou"
    if "budget" in m or "timeout" in m:
        return "orcamento"
    if m.startswith("interrupted"):
        return "interrompido"
    return "caiu" if not m else f"outro:{m}"


def decidir(obs: dict, mem: dict, agora: float, lim: dict = LIM) -> dict:
    """obs = {log, rodada, saude, pausa}. mem = memória da vigia (é atualizada aqui). Devolve {estado, acoes, causa}."""
    lg, rd, sd = obs["log"], obs["rodada"], obs["saude"]
    acoes = []
    if sd.get("trava") == "morta":
        acoes.append("liberar_trava")
    # progresso real zera as contagens (regra de dois e críticas)
    if rd["tentativas"] > mem.get("contagem", 0) or (rd["melhor_nota"] is not None and
                                                    (mem.get("melhor") is None or rd["melhor_nota"] < mem["melhor"])):
        mem.update(contagem=rd["tentativas"], melhor=rd["melhor_nota"], progresso_ts=agora, causas=[], nao=0)
    mem.setdefault("progresso_ts", agora)
    if obs.get("pausa"):
        return {"estado": "pausado", "acoes": [], "causa": None}
    if agora >= lim.get("fim_ts", float("inf")):
        return {"estado": "prazo_encerrado", "acoes": [], "causa": None}  # barreira: depois do prazo, só observa
    if mem.get("desistiu"):
        return {"estado": "desistiu", "acoes": [], "causa": mem["desistiu"]}
    if rd["terminou"]:
        return {"estado": "terminou", "acoes": acoes + ["encerrar"], "causa": None}
    if not sd.get("modelo"):
        return {"estado": "infra_fora", "acoes": acoes, "causa": "modelo"}
    if lg["sessao"] is None and not mem.get("relanco_pendente"):
        return {"estado": "sem_sessao", "acoes": acoes, "causa": None}  # nada vigiado ainda: não age no escuro
    ocioso = (agora - max(lg["ultima_atividade"], lg["fim_turno"], lg["inicio_turno"])) / 60
    sem_prog = (agora - mem["progresso_ts"]) / 60
    trabalhando_fora = sd.get("trava") == "viva" or (sd.get("scripts_da_rodada") or 0) > 0 or bool(rd.get("pendente"))
    if lg["turno_ativo"]:
        if ocioso >= lim["silencio_caiu_min"] and not trabalhando_fora:
            causa = "caiu"
        else:
            if sem_prog >= lim["sem_progresso_min"] and (agora - mem.get("critica_ts", 0)) / 60 >= lim["critica_cada_min"]:
                acoes.append("criticar")  # durante o turno só dá para perguntar e avisar; o turno não é interrompido
            return {"estado": "trabalhando" if sem_prog < lim["sem_progresso_min"] else "sem_progresso", "acoes": acoes,
                    "causa": None}
    elif ocioso < lim["ocioso_min"]:
        return {"estado": "entre_turnos", "acoes": acoes, "causa": None}
    else:
        causa = "estado_parcial" if rd["ultimo_especial"] == "estado_parcial" else _causa(lg["motivo_fim"])
    if not sd.get("unreal"):
        return {"estado": "infra_fora", "acoes": acoes, "causa": "unreal"}
    pend = mem.get("relanco_pendente")
    if pend and (agora - pend) / 60 < lim["espera_relanco_min"]:
        return {"estado": "relancando", "acoes": acoes, "causa": causa}  # a sessão nova ainda não apareceu no log
    if pend:
        mem["desistiu"] = "o relançamento não abriu sessão nova (veja relanco_*_saida.txt)"
        return {"estado": "parou", "acoes": acoes + ["avisar"], "causa": "relanco_falhou"}
    if len(mem.get("relancos", [])) >= lim["relancos_noite"]:
        mem["desistiu"] = "teto de relançamentos da noite"
        return {"estado": "parou", "acoes": acoes + ["avisar"], "causa": causa}
    if len([t for t in mem.get("relancos", []) if agora - t < 3600]) >= lim["relancos_hora"]:
        return {"estado": "teto_da_hora", "acoes": acoes, "causa": causa}  # espera a hora virar
    repetida = 0 if causa == "orcamento" else sum(1 for c in mem.get("causas", []) if c == causa)
    if repetida == 0:
        acoes.append("relancar")
    elif repetida == 1:
        acoes.append("relancar_mudando")
    else:
        acoes.append("criticar_e_decidir")
    return {"estado": "parou", "acoes": acoes, "causa": causa}


# ---------- ações ----------
def _registrar(nome: str, d: dict):
    os.makedirs(PASTA, exist_ok=True)
    with open(os.path.join(PASTA, nome), "a", encoding="utf-8") as f:
        f.write(json.dumps(dict(quando=dt.datetime.now().isoformat(timespec="seconds"), **d), ensure_ascii=False,
                           default=str) + "\n")


def prompt_corrigido(pedido: str, rodada: str, rd: dict, causa: str, mudar: bool) -> str:
    pedido, rodada = os.path.abspath(pedido), os.path.abspath(rodada)  # o terminal do Runtime começa em <shared drive>
    ult = "; ".join(f"n={u['n']} {u['tipo']} nota={u['nota']} {u['classe_erro']}" for u in rd["ultimas"]) or "nenhuma"
    return (f"{PREFIXO} Antes de qualquer comando: cd {RAIZ} (nunca grave em Y:). Continue a rodada descrita em {pedido} (leia o pedido inteiro de novo; as regras valem todas). "
            f"NÃO recomece do zero: o estado está em {rodada} (tentativas.jsonl, encaixes.jsonl, LICOES.md, "
            f"criticas.md). Até agora: {rd['tentativas']} tentativas, melhor nota {rd['melhor_nota']}, "
            f"{rd['linhagens_fechadas']} linhagens fechadas; últimas: {ult}.\n"
            f"Por que a sessão anterior parou ({causa}): {CONSELHO.get(causa, 'motivo não identificado: ' + causa)}\n"
            + (MUDAR + "\n" if mudar else "")
            + "Comece rodando `fila_executor.py estado` (campeãs, linhagens, pendente) e lendo LICOES.md; diga em 2 linhas o "
              "próximo passo e siga. Depois das 07:30 o executor recusa tentativas novas: escreva o FECHAMENTO.md.")


def relancar(texto: str, mem: dict, seco: bool) -> dict:
    arq = os.path.join(PASTA, f"relanco_{int(time.time())}.txt")
    if seco:
        return {"seco": True, "prompt": texto[:300]}
    os.makedirs(PASTA, exist_ok=True)
    open(arq, "w", encoding="utf-8").write(texto)
    saida = open(arq.replace(".txt", "_saida.txt"), "w", encoding="utf-8")
    orc = int(min(LIM["run_budget_s"], max(60, LIM.get("fim_ts", time.time() + 10**6) - time.time())))
    subprocess.Popen(["cmd", "/c", HERMES_CMD, "-p", PERFIL, "chat", "--query-file", arq, "-Q",
                      "--max-turns", str(LIM["max_turns"]), "--run-budget", str(orc), "--in", RAIZ],
                     cwd=RAIZ, stdout=saida, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                     creationflags=0x00000008 | 0x00000200)  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    mem.setdefault("relancos", []).append(time.time())
    mem["relanco_pendente"] = time.time()
    return {"prompt_arquivo": arq}


def criticar(rd: dict, rodada: str, seco: bool) -> str:
    """Crítico de olhos frescos: outra sessão do Qwen, só com um resumo curto. Devolve 'sim', 'nao' ou 'indefinido'."""
    crit = os.path.join(rodada, "criticas.md")
    ult_crit = open(crit, encoding="utf-8", errors="replace").read()[-600:] if os.path.exists(crit) else "(sem críticas)"
    texto = (f"{PREFIXO_CRITICO} Você é um crítico. Não use ferramentas. Um agente tenta montar uma fila de movimentos por "
             f"tentativa e erro; nota menor é melhor, 0 = passou. Resumo: {rd['tentativas']} tentativas, melhor nota "
             f"{rd['melhor_nota']}, {rd['linhagens_fechadas']} linhagens fechadas. Últimas: {json.dumps(rd['ultimas'], ensure_ascii=False)}. "
             f"Notas dele: {ult_crit}\nResponda na PRIMEIRA linha só SIM ou NAO: está progredindo de verdade? "
             "Na segunda, uma frase com o porquê.")
    if seco:
        return "indefinido"
    os.makedirs(PASTA, exist_ok=True)
    arq = os.path.join(PASTA, f"critica_{int(time.time())}.txt")
    open(arq, "w", encoding="utf-8").write(texto)
    try:
        r = subprocess.run(["cmd", "/c", HERMES_CMD, "-p", PERFIL, "chat", "--query-file", arq, "-Q",
                            "--max-turns", "2", "--run-budget", "300"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600, cwd=RAIZ, stdin=subprocess.DEVNULL)
        resp = r.stdout or ""
    except subprocess.TimeoutExpired:
        resp = ""
    open(arq.replace(".txt", "_resposta.txt"), "w", encoding="utf-8").write(resp)
    return veredito(resp)


def veredito(resp: str) -> str:
    for ln in resp.splitlines():
        p = ln.strip().strip("*").upper()
        if p.startswith("SIM"):
            return "sim"
        if p.startswith(("NAO", "NÃO")):
            return "nao"
    return "indefinido"


def avisar(motivo: str, obs: dict):
    os.makedirs(PASTA, exist_ok=True)
    with open(os.path.join(PASTA, "AVISO.md"), "a", encoding="utf-8") as f:
        f.write(f"- {dt.datetime.now():%d/%m %H:%M} · a vigia parou de agir: {motivo}. Rodada: "
                f"{obs['rodada']['tentativas']} tentativas, melhor nota {obs['rodada']['melhor_nota']}.\n")


def executar(dec: dict, obs: dict, mem: dict, args) -> list:
    res = []
    for a in dec["acoes"]:
        if a == "liberar_trava":
            r = {} if args.seco else T.liberar_orfa(TRAVA, os.path.join(PASTA, "trava.log"))
            res.append({"acao": a, "resultado": r.get("liberada", "seco")})
        elif a in ("relancar", "relancar_mudando"):
            mem.setdefault("causas", []).append(dec["causa"])
            r = relancar(prompt_corrigido(args.pedido, args.rodada, obs["rodada"], dec["causa"], a == "relancar_mudando"),
                         mem, args.seco)
            res.append({"acao": a, "resultado": r})
        elif a in ("criticar", "criticar_e_decidir"):
            mem["critica_ts"] = time.time()
            v = criticar(obs["rodada"], args.rodada, args.seco)
            if v == "sim":
                mem["nao"], mem["indefinidos"] = 0, 0
            elif v == "nao":
                mem["nao"] = mem.get("nao", 0) + 1
            else:
                mem["indefinidos"] = mem.get("indefinidos", 0) + 1  # não é "não": pergunta de novo na próxima vez
            res.append({"acao": a, "resultado": v, "nao_seguidos": mem.get("nao", 0), "indefinidos": mem.get("indefinidos", 0)})
            motivo = (f"crítico disse NÃO {mem['nao']} vezes seguidas" if mem.get("nao", 0) >= 2 else
                      f"crítico sem resposta legível {mem['indefinidos']} vezes" if mem.get("indefinidos", 0) >= 2 else
                      "crítico disse NÃO na 3ª parada pelo mesmo motivo" if a == "criticar_e_decidir" and v == "nao" else None)
            if motivo:
                mem["desistiu"] = motivo
                avisar(motivo, obs)
                res.append({"acao": "avisar", "resultado": motivo})
            elif a == "criticar_e_decidir" and v == "sim":
                mem.setdefault("causas", []).append(dec["causa"])
                res.append({"acao": "relancar_mudando", "resultado": relancar(
                    prompt_corrigido(args.pedido, args.rodada, obs["rodada"], dec["causa"], True), mem, args.seco)})
        elif a == "avisar":
            avisar(mem.get("desistiu", dec["causa"]), obs)
            res.append({"acao": a, "resultado": mem.get("desistiu")})
    return res


# ---------- laço ----------
def observar(args, mem) -> dict:
    linhas = []
    if os.path.exists(LOG_DEV):
        with open(LOG_DEV, encoding="utf-8", errors="replace") as f:
            linhas = f.readlines()[-6000:]
    lg = ler_log(linhas, set(mem["sessoes"]))
    for s in lg["novas"]:
        if s not in mem["sessoes"]:
            mem["sessoes"].append(s)
            mem.pop("relanco_pendente", None)
    return {"log": lg, "rodada": ler_rodada(args.rodada), "saude": saude(),
            "pausa": os.path.exists(os.path.join(PASTA, "PAUSA"))}


def sessao_inicial() -> str | None:
    """A sessão principal mais recente do hermes-dev (a que o operador abriu)."""
    if not os.path.exists(LOG_DEV):
        return None
    sid = None
    with open(LOG_DEV, encoding="utf-8", errors="replace") as f:
        for ln in f.readlines()[-6000:]:
            m = _RE_LINHA.match(ln.rstrip("\n"))
            if m and m.group(2) and "conversation turn:" in m.group(3) and "msg='Review the conve" not in m.group(3):
                sid = m.group(2)
    return sid


def resumo():
    arq = os.path.join(PASTA, "intervencoes.jsonl")
    linhas = [json.loads(ln) for ln in open(arq, encoding="utf-8")] if os.path.exists(arq) else []
    causas, acoes = {}, {}
    for d in linhas:
        causas[d.get("causa")] = causas.get(d.get("causa"), 0) + 1
        for r in d.get("resultados", []):
            acoes[r["acao"]] = acoes.get(r["acao"], 0) + 1
    txt = (f"# Resumo da vigia ({dt.datetime.now():%d/%m %H:%M})\n\n- intervenções: {len(linhas)}\n"
           f"- por causa: {causas}\n- ações: {acoes}\n\n## Linha a linha\n" +
           "".join(f"- {d['quando']} · {d['estado']} · causa {d.get('causa')} · {d.get('resultados')} · "
                   f"tentativas {d.get('tentativas')} → depois veja se subiu\n" for d in linhas))
    os.makedirs(PASTA, exist_ok=True)
    open(os.path.join(PASTA, "RESUMO.md"), "w", encoding="utf-8").write(txt)
    return txt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rodada", default=os.path.join("work", "fila_2026-10-07"))
    ap.add_argument("--pedido", default=os.path.join("escaladas", "2026-10-07-RODADA-fila-de-movimentos.md"))
    ap.add_argument("--sessao", help="sessão do hermes-dev a vigiar (padrão: a mais recente)")
    ap.add_argument("--ate", default="08:00")
    ap.add_argument("--uma-vez", action="store_true")
    ap.add_argument("--seco", action="store_true", help="decide e mostra, mas não age")
    ap.add_argument("--resumo", action="store_true")
    ap.add_argument("--perfil", default="hermes-dev", help="perfil do Hermes a vigiar e relançar")
    ap.add_argument("--pasta", help="onde a vigia guarda o próprio estado (padrão work/vigia; o teste usa outra)")
    ap.add_argument("--intervalo", type=int, help="segundos entre checagens (padrão 300)")
    ap.add_argument("--max-turns", type=int, help="teto de chamadas por turno nas sessões relançadas (padrão 200)")
    ap.add_argument("--run-budget", type=int, help="teto de segundos por sessão relançada (padrão 5400)")
    ap.add_argument("--ocioso-min", type=float, help="minutos parado antes de agir (padrão 10)")
    args = ap.parse_args()
    global PASTA, PERFIL, LOG_DEV
    PERFIL = args.perfil
    LOG_DEV = os.path.join(HERMES_DIR, "profiles", PERFIL, "logs", "agent.log")
    if args.pasta:
        PASTA = os.path.abspath(args.pasta)
    for k, v in (("intervalo_s", args.intervalo), ("max_turns", args.max_turns), ("run_budget_s", args.run_budget),
                 ("ocioso_min", args.ocioso_min)):
        if v is not None:
            LIM[k] = v
    os.chdir(RAIZ)
    if args.resumo:
        print(resumo())
        return 0
    os.makedirs(PASTA, exist_ok=True)
    os.makedirs(PASTA, exist_ok=True)
    arq_mem = os.path.join(PASTA, "memoria.json")
    mem = json.load(open(arq_mem, encoding="utf-8")) if os.path.exists(arq_mem) and not args.seco else {}
    if "sessoes" not in mem:  # "nenhuma" = só as sessões que a própria vigia lançar (teste)
        mem["sessoes"] = [] if args.sessao == "nenhuma" else [s for s in [args.sessao or sessao_inicial()] if s]
    h, m = map(int, args.ate.split(":"))
    fim = dt.datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
    if fim <= dt.datetime.now():
        fim += dt.timedelta(days=1)
    LIM["fim_ts"] = fim.timestamp()  # barreira: depois disso a vigia só observa
    _registrar("vigia.log", {"evento": "inicio", "sessoes": mem["sessoes"], "rodada": args.rodada, "ate": str(fim),
                             "seco": args.seco})
    while True:
        if os.path.exists(os.path.join(PASTA, "PARAR")):
            _registrar("vigia.log", {"evento": "parada", "motivo": "arquivo PARAR"})
            break
        obs = observar(args, mem)
        dec = decidir(obs, mem, time.time())
        res = executar(dec, obs, mem, args)
        linha = {"estado": dec["estado"], "causa": dec["causa"], "tentativas": obs["rodada"]["tentativas"],
                 "melhor_nota": obs["rodada"]["melhor_nota"], "turno_ativo": obs["log"]["turno_ativo"],
                 "contexto_in": obs["log"]["contexto_in"], "saude": obs["saude"], "sessoes": mem["sessoes"][-3:]}
        _registrar("vigia.log", linha)
        if res:
            _registrar("intervencoes.jsonl", dict(linha, resultados=res, evidencia={
                "motivo_fim": obs["log"]["motivo_fim"], "ultimas": obs["rodada"]["ultimas"]}))
        print(json.dumps(dict(linha, acoes=res), ensure_ascii=False, default=str), flush=True)
        if not args.seco:
            json.dump(mem, open(arq_mem, "w", encoding="utf-8"), ensure_ascii=False)
        if args.uma_vez or dec["estado"] in ("terminou", "desistiu") or dt.datetime.now() >= fim:
            break
        time.sleep(LIM["intervalo_s"])
    resumo()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        _registrar("vigia.log", {"evento": "parada", "motivo": "Ctrl+C"})
