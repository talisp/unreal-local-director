"""Painel do Director no navegador (só no computador do operador: http://127.0.0.1:8765).

Mostra, atualizando sozinho: o que está rodando agora, o teste no Unreal (gráfico das notas, a melhor receita, os
vídeos e as variações), as ideias do júnior, a bateria e o Astra, o que falta do operador, os resultados (.md) e o
HISTÓRICO do que foi feito, em tempo real. Lê só os arquivos que as linhas já gravam; não mexe no Unreal nem no Hermes.

Botões: abrir um resultado ou detalhe (.md, vídeo), escolher a variação (tools/escolha.py), aprovar ou recusar uma
ideia (ideias/decisoes.jsonl), parar a vigia (work/vigia/PARAR) e RODAR as rotinas (júnior, bateria, ensaio, noite,
Astra; o navegador pede confirmação nas que gastam Unreal ou cota). Cada rotina abre numa janela própria, minimizada e
sem roubar o foco (tools/rotina.py --sim --sem-navegador); a mesma rotina não roda duas vezes ao mesmo tempo.

Uso: venv\\Scripts\\python.exe tools\\painel.py [--porta 8765] [--sem-abrir]
"""
import argparse
import datetime as dt
import glob
import html
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
sys.path.insert(0, os.path.join(RAIZ, "tools"))
from unreal_macros import cena as C  # noqa: E402  # pyright: ignore[reportMissingImports]
from unreal_macros import fila as F  # noqa: E402  # pyright: ignore[reportMissingImports]

PORTA = 8765
RESULTADOS = os.path.join(RAIZ, "resultados")
HISTORICO = os.path.join(RESULTADOS, "historico.jsonl")
DECISOES_IDEIAS = os.path.join(RAIZ, "ideias", "decisoes.jsonl")
CENA_PADRAO = os.path.join(RAIZ, "cenas", "fila.md")
PARAR_VIGIA = os.path.join(RAIZ, "work", "vigia", "PARAR")
ABRIVEIS = re.compile(r"^(resultados/[^/]+\.md|ideias/[^/]+\.md|escaladas/[^/]+\.md|work/[^/]+/[A-Z_]+\.md|"
                      r"work/[^/]+/videos(/t\d{3}\.mp4)?|work/vigia/RESUMO\.md)$")
VIDEO = re.compile(r"^work/[^/]+/videos/t\d{3}\.mp4$")


# ---------- leitura ----------
def _rel(p: str) -> str:
    return os.path.relpath(p, RAIZ).replace("\\", "/")


def _json(p: str):
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _jsonl(p: str) -> list:
    out = []
    if os.path.exists(p):
        for ln in open(p, encoding="utf-8", errors="replace"):
            try:
                out.append(json.loads(ln))
            except ValueError:
                pass
    return out


def _mtime_iso(p: str) -> str:
    return dt.datetime.fromtimestamp(os.path.getmtime(p)).isoformat(timespec="seconds")


def _git_head() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=RAIZ, capture_output=True, timeout=30,
                           creationflags=0x08000000)  # CREATE_NO_WINDOW: nunca pisca janela
        return r.stdout.decode().strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def rodada_atual(raiz: str = RAIZ) -> str | None:
    """A rodada mais nova no Unreal: pasta de work/ com LANCAMENTO.json ou tentativas.jsonl."""
    cand = glob.glob(os.path.join(raiz, "work", "*", "LANCAMENTO.json")) + \
        glob.glob(os.path.join(raiz, "work", "*", "tentativas.jsonl"))
    cand = [c for c in cand if "bateria" not in c and "testes" not in c]
    return os.path.dirname(max(cand, key=os.path.getmtime)) if cand else None


def ler_ideias(raiz: str = RAIZ) -> list:
    decisoes = {(d["arquivo"], d["n"]): d["decisao"] for d in _jsonl(os.path.join(raiz, "ideias", "decisoes.jsonl"))}
    out = []
    for arq in sorted(glob.glob(os.path.join(raiz, "ideias", "*.md")), reverse=True):
        texto = open(arq, encoding="utf-8", errors="replace").read()
        rel = os.path.relpath(arq, raiz).replace("\\", "/")
        partes = re.split(r"^## (\d+)\. (.+)$", texto, flags=re.M)
        for i in range(1, len(partes) - 2, 3):
            n, titulo, bloco = int(partes[i]), partes[i + 1].strip(), partes[i + 2]

            def campo(nome, b=bloco):
                m = re.search(rf"\*\*{nome}:\*\*\s*(.+)", b)
                return m.group(1).strip() if m else ""
            out.append({"arquivo": rel, "n": n, "titulo": titulo, "problema": campo("Problema"),
                        "ideia": campo("Ideia"), "custo": campo("Custo"), "decisao": decisoes.get((rel, n))})
    return out


def dados_unreal(pasta: str | None) -> dict | None:
    if not pasta:
        return None
    regs = _jsonl(os.path.join(pasta, "tentativas.jsonl"))
    tent = [t for t in regs if t.get("tipo_linha") == "tentativa"]
    validas = [t for t in tent if (t.get("avaliacao") or {}).get("valida")]
    lanc = _json(os.path.join(pasta, "LANCAMENTO.json")) or {}
    cena = C.ler_cena(CENA_PADRAO) if lanc.get("cena") in (None, "fila") else None
    k = (cena or {}).get("variacoes", 0) if lanc else 0

    def video(n):
        v = os.path.join(pasta, "videos", f"t{n:03d}.mp4")
        return _rel(v) if os.path.exists(v) else None
    notas = [t for t in validas if isinstance(t.get("nota"), (int, float))]
    melhor = min(notas, key=lambda t: (t["nota"], -t["n"])) if notas else None
    ev = C.estado_variacoes(validas, k) if k else None
    escolha = _json(os.path.join(pasta, "escolha.json")) or {}
    opcoes = []
    if ev and ev["base"] is not None:
        opcoes = [{"opcao": "base", "n": ev["base"], "video": video(ev["base"])}] + \
                 [{"opcao": str(n), "n": n, "video": video(n)} for n in ev["aceitas"]]
    detalhes = [_rel(os.path.join(pasta, x)) for x in ("FECHAMENTO.md", "ENSAIO.md") if os.path.exists(os.path.join(pasta, x))]
    return {"rodada": os.path.basename(pasta), "pasta": _rel(pasta), "modo": lanc.get("modo"), "inicio": lanc.get("quando"),
            "tentativas": len(tent),
            "pontos": [{"n": t["n"], "nota": t.get("nota"), "valida": (t.get("avaliacao") or {}).get("valida", False),
                        "variacao": bool(t.get("variacao"))} for t in tent],
            "melhor": None if not melhor else {"n": melhor["n"], "nota": melhor["nota"], "video": video(melhor["n"]),
                                               "clipes": [p.get("clipe") for p in melhor.get("receita") or []]},
            "sucesso": F.sucesso(validas), "variacoes_pedidas": k,
            "variacoes": None if not ev else {"fase": ev["fase"], "faltam": ev["faltam"], "opcoes": opcoes},
            "escolhida": escolha.get("escolhida"), "detalhes": detalhes,
            "fechou": bool(detalhes), "tem_videos": os.path.isdir(os.path.join(pasta, "videos"))}


def vigia_agora(raiz: str = RAIZ) -> dict | None:
    linhas = _jsonl(os.path.join(raiz, "work", "vigia", "vigia.log"))
    est = [x for x in linhas if "estado" in x]
    return est[-1] if est else None


def junior_agora(raiz: str = RAIZ, agora: float | None = None) -> dict | None:
    """Júnior rodando = sessao.jsonl mexido nos últimos 10 min e ainda sem resumo.json."""
    import time
    agora = agora or time.time()
    s = glob.glob(os.path.join(raiz, "work", "junior", "*", "sessao.jsonl"))
    if not s:
        return None
    arq = max(s, key=os.path.getmtime)
    if agora - os.path.getmtime(arq) > 600 or os.path.exists(os.path.join(os.path.dirname(arq), "resumo.json")):
        return None
    acoes = [e for e in _jsonl(arq) if e.get("type") == "tool_use"]
    ult = [f"{e.get('name')}: {json.dumps(e.get('input') or {}, ensure_ascii=False)[:90]}" for e in acoes[-5:]]
    return {"pasta": _rel(os.path.dirname(arq)), "acoes": len(acoes), "ultimas": ult}


def historico(raiz: str = RAIZ, pasta_rodada: str | None = None, limite: int = 80) -> list:
    """[{quando, linha, texto, abrir?}] do mais novo para o mais velho: o que foi feito, de todas as fontes."""
    ev = []
    for d in _jsonl(os.path.join(raiz, "resultados", "historico.jsonl")):
        ev.append({"quando": d.get("quando"), "linha": d.get("linha"), "texto": d.get("texto"), "abrir": d.get("arquivo")})
    if pasta_rodada:
        nome = os.path.basename(pasta_rodada)
        for t in _jsonl(os.path.join(pasta_rodada, "tentativas.jsonl")):
            tl, q = t.get("tipo_linha"), t.get("quando")
            if tl == "tentativa":
                clipes = " → ".join(p.get("clipe", "?") for p in t.get("receita") or [])
                val = (t.get("avaliacao") or {}).get("valida")
                ev.append({"quando": q, "linha": "unreal", "texto": f"tentativa {t.get('n')}: nota "
                           f"{t.get('nota') if val else 'inválida'}{' (variação)' if t.get('variacao') else ''} · {clipes}"})
            elif tl == "tentativa_interrompida":
                ev.append({"quando": q, "linha": "unreal", "texto": f"tentativa {t.get('n')} caiu (registrada como interrompida)"})
            elif tl == "linhagem_fechada":
                ev.append({"quando": q, "linha": "unreal", "texto": f"linhagem {t.get('linhagem')} fechada: {t.get('motivo')}"})
        inicio = (_json(os.path.join(pasta_rodada, "LANCAMENTO.json")) or {}).get("quando", "")
        for d in _jsonl(os.path.join(raiz, "work", "vigia", "intervencoes.jsonl")):
            if d.get("quando", "") >= inicio:
                acoes = ", ".join(r.get("acao", "?") for r in d.get("resultados") or [])
                ev.append({"quando": d.get("quando"), "linha": "vigia", "texto": f"{acoes} (motivo: {d.get('causa')})"})
        for x in ("FECHAMENTO.md", "ENSAIO.md"):
            p = os.path.join(pasta_rodada, x)
            if os.path.exists(p):
                ev.append({"quando": _mtime_iso(p), "linha": "unreal", "texto": f"{nome}: o Productor escreveu {x}",
                           "abrir": _rel(p)})
    baterias = sorted(glob.glob(os.path.join(raiz, "work", "bateria", "*", "RESUMO.json")), key=os.path.getmtime)
    for p in baterias[-5:]:  # só as 5 últimas: a bateria roda a cada commit e afogaria o resto
        r = _json(p) or {}
        ev.append({"quando": _mtime_iso(p), "linha": "bateria",
                   "texto": f"bateria {'OK' if r.get('ok') else 'FALHOU'} no commit {r.get('commit', '?')}"})
    for p in glob.glob(os.path.join(raiz, "work", "junior", "*", "resumo.json")):
        r = _json(p) or {}
        ev.append({"quando": _mtime_iso(p), "linha": "junior", "texto": f"júnior: {len(r.get('ideias') or [])} ideias "
                   f"sobre {((r.get('tema') or {}).get('tema')) or '?'}", "abrir": r.get("arquivo")})
    for p in glob.glob(os.path.join(raiz, "escaladas", "*-ASTRA-*.md")):
        ev.append({"quando": _mtime_iso(p), "linha": "astra", "texto": f"Astra: revisão {os.path.basename(p)[:-3]}",
                   "abrir": _rel(p)})
    for d in _jsonl(os.path.join(raiz, "ideias", "decisoes.jsonl")):
        ev.append({"quando": d.get("quando"), "linha": "talis", "texto": f"ideia {d.get('n')} de {d.get('arquivo')}: "
                   f"{d.get('decisao')}"})
    ev = [e for e in ev if e.get("quando")]
    ev.sort(key=lambda e: e["quando"], reverse=True)
    return ev[:limite]


def pendencias_do_talis(u: dict | None, ideias: list, bateria_ok: bool | None, raiz: str = RAIZ) -> list:
    out = []
    modos = {(_json(p) or {}).get("modo") for p in glob.glob(os.path.join(raiz, "work", "*", "LANCAMENTO.json"))}
    if "ensaio" not in modos:
        out.append({"texto": "Lançar o ensaio no Unreal (atalho \"3 - Unreal ENSAIO\").", "alvo": None})
    elif "noite" not in modos:
        out.append({"texto": "Se o ensaio foi bem, lançar a noite (atalho \"4 - Unreal NOITE\").", "alvo": None})
    if u and u.get("variacoes") and u["variacoes"]["opcoes"] and u.get("escolhida") is None and u.get("fechou"):
        out.append({"texto": "Escolher a melhor variação da última rodada.", "alvo": "unreal"})
    abertas = [i for i in ideias if not i["decisao"]]
    if abertas:
        out.append({"texto": f"Aprovar ou recusar {len(abertas)} ideia(s) do júnior.", "alvo": "ideias"})
    if bateria_ok is False:
        out.append({"texto": "A bateria falhou no código atual: chamar o Claude.", "alvo": "bateria"})
    return out


def resultados(raiz: str = RAIZ, limite: int = 20) -> list:
    xs = sorted(glob.glob(os.path.join(raiz, "resultados", "*.md")), key=os.path.getmtime, reverse=True)[:limite]
    return [{"nome": os.path.basename(x)[:-3], "abrir": os.path.relpath(x, raiz).replace("\\", "/")} for x in xs]


def dados() -> dict:
    pasta = rodada_atual()
    u = dados_unreal(pasta)
    head = _git_head()
    bat = _json(os.path.join(RAIZ, "work", "bateria", head, "RESUMO.json"))
    ast = glob.glob(os.path.join(RAIZ, "escaladas", "*-ASTRA-*.md"))
    ast_ult = max(ast, key=os.path.getmtime) if ast else None
    ast_n = len(re.findall(r"^\| \d+ \| (alta|media|baixa) \|", open(ast_ult, encoding="utf-8").read(), re.M)) if ast_ult else 0
    ideias = ler_ideias()
    vig = vigia_agora()
    return {"agora": dt.datetime.now().isoformat(timespec="seconds"),
            "rodando": {"junior": junior_agora(), "vigia": vig,
                        "unreal": bool(u and u.get("modo") and not u.get("fechou") and vig and
                                       vig.get("estado") not in ("terminou", "desistiu", "prazo_encerrado")),
                        "parar_pedido": os.path.exists(PARAR_VIGIA)},
            "unreal": u, "ideias": ideias,
            "bateria": None if not bat else {"ok": bat["ok"], "commit": bat["commit"], "minutos": round(bat["duracao_s"] / 60, 1),
                                             "falhas": [f"{e['nome']}: {e.get('detalhe_curto', '')}" for e in bat["etapas"] if not e["ok"]]},
            "bateria_commit_atual": head,
            "astra": None if not ast_ult else {"arquivo": _rel(ast_ult), "nome": os.path.basename(ast_ult)[:-3], "achados": ast_n},
            "falta_voce": pendencias_do_talis(u, ideias, None if not bat else bat["ok"]),
            "resultados": resultados(), "historico": historico(pasta_rodada=pasta),
            "ocupadas": ocupadas(bool(u and u.get("modo") and not u.get("fechou") and vig and
                                      vig.get("estado") not in ("terminou", "desistiu", "prazo_encerrado")))}


# ---------- rodar as rotinas (botões) ----------
BOTOES = ("junior", "bateria", "ensaio", "noite", "astra")
LIMITE_MIN = {"junior": 60, "bateria": 20, "astra": 30, "ensaio": 150, "noite": 14 * 60}  # 'começou' sem fim, depois disso, deixa rodar de novo
LANCADOS: dict = {}  # linha -> processo lançado por este painel


def ocupadas(unreal_rodando: bool, raiz: str = RAIZ, agora: dt.datetime | None = None) -> list:
    """Linhas que não podem ser lançadas agora: já rodando (por este painel ou por um atalho)."""
    agora = agora or dt.datetime.now()
    out = {x for x, p in LANCADOS.items() if p.poll() is None}
    ultimo = {}
    for d in _jsonl(os.path.join(raiz, "resultados", "historico.jsonl")):
        ultimo[d.get("linha")] = d
    for x, d in ultimo.items():
        if x in LIMITE_MIN and str(d.get("texto", "")).startswith("começou") and \
                agora - dt.datetime.fromisoformat(d["quando"]) < dt.timedelta(minutes=LIMITE_MIN[x]):
            out.add(x)
    if unreal_rodando or out & {"ensaio", "noite"}:
        out |= {"ensaio", "noite"}  # um teste no Unreal por vez
    return sorted(out)


def rodar_rotina(linha: str, pergunta: str = "") -> dict:
    import rotina as RO  # pyright: ignore[reportMissingImports]
    if linha not in BOTOES:
        return {"ok": False, "erro": f"rotina desconhecida: {linha}"}
    u = dados_unreal(rodada_atual())
    vig = vigia_agora()
    if linha in ocupadas(bool(u and u.get("modo") and not u.get("fechou") and vig and
                              vig.get("estado") not in ("terminou", "desistiu", "prazo_encerrado"))):
        return {"ok": False, "erro": "essa rotina já está rodando"}
    cmd = [os.path.join(RAIZ, "venv", "Scripts", "python.exe"), os.path.join(RAIZ, "tools", "rotina.py"), linha,
           "--sim", "--sem-navegador"] + (["--pergunta", pergunta[:2000]] if linha == "astra" and pergunta else [])
    # janela própria, minimizada e sem foco: não tira o operador de onde ele digita
    LANCADOS[linha] = subprocess.Popen(cmd, cwd=RAIZ, creationflags=RO.NOVA_JANELA, startupinfo=RO.janela_minimizada())
    return {"ok": True}


# ---------- ações (botões) ----------
def abrir(rel: str) -> None:
    os.startfile(os.path.join(RAIZ, rel))  # type: ignore[attr-defined]


def acao(d: dict) -> dict:
    tipo = d.get("acao")
    if tipo == "abrir":
        rel = str(d.get("arquivo", ""))
        if not ABRIVEIS.match(rel) or not os.path.exists(os.path.join(RAIZ, rel)):
            return {"ok": False, "erro": "arquivo fora da lista do painel"}
        abrir(rel)
        return {"ok": True}
    if tipo == "ideia":
        if d.get("decisao") not in ("aprovada", "recusada"):
            return {"ok": False, "erro": "decisão inválida"}
        alvo = next((i for i in ler_ideias() if i["arquivo"] == d.get("arquivo") and i["n"] == d.get("n")), None)
        if not alvo:
            return {"ok": False, "erro": "ideia não encontrada"}
        with open(DECISOES_IDEIAS, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"arquivo": alvo["arquivo"], "n": alvo["n"], "titulo": alvo["titulo"],
                                "decisao": d["decisao"], "por": "Talis (painel)",
                                "quando": dt.datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False) + "\n")
        return {"ok": True}
    if tipo == "escolher":
        import escolha as E  # pyright: ignore[reportMissingImports]
        pasta = rodada_atual()
        if not pasta:
            return {"ok": False, "erro": "não há rodada"}
        try:
            if not os.path.exists(os.path.join(pasta, "escolha.json")):
                E.gerar(pasta, None, (_json(os.path.join(pasta, "LANCAMENTO.json")) or {}).get("cena"))
            reg = E.escolher(pasta, str(d.get("opcao")))
        except ValueError as e:
            return {"ok": False, "erro": str(e)}
        return {"ok": True, "id": reg["id"]}
    if tipo == "rodar":
        return rodar_rotina(str(d.get("linha", "")), str(d.get("pergunta") or ""))
    if tipo == "parar_vigia":
        os.makedirs(os.path.dirname(PARAR_VIGIA), exist_ok=True)
        open(PARAR_VIGIA, "w", encoding="utf-8").write(f"pedido pelo operador no painel {dt.datetime.now():%d/%m %H:%M}\n")
        return {"ok": True}
    return {"ok": False, "erro": f"ação desconhecida: {tipo}"}


# ---------- servidor ----------
def pagina(token: str) -> str:
    return open(os.path.join(RAIZ, "tools", "painel.html"), encoding="utf-8").read().replace("{{TOKEN}}", html.escape(token))


def servidor(porta: int, token: str) -> ThreadingHTTPServer:
    hosts = {f"127.0.0.1:{porta}", f"localhost:{porta}"}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silencioso
            pass

        def _enviar(self, codigo: int, corpo: bytes, tipo: str):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)

        def _host_ok(self) -> bool:
            return self.headers.get("Host", "") in hosts  # barra páginas de fora que apontam um nome para 127.0.0.1

        def do_GET(self):
            if not self._host_ok():
                return self._enviar(403, b"host", "text/plain")
            caminho, _, q = self.path.partition("?")
            if caminho == "/":
                return self._enviar(200, pagina(token).encode("utf-8"), "text/html; charset=utf-8")
            if caminho == "/api/dados":
                return self._enviar(200, json.dumps(dados(), ensure_ascii=False, default=str).encode("utf-8"),
                                    "application/json; charset=utf-8")
            if caminho == "/video":
                from urllib.parse import parse_qs
                rel = (parse_qs(q).get("p") or [""])[0]
                arq = os.path.join(RAIZ, rel)
                if not VIDEO.match(rel) or not os.path.exists(arq):
                    return self._enviar(404, b"video", "text/plain")
                return self._enviar(200, open(arq, "rb").read(), "video/mp4")
            return self._enviar(404, b"nada", "text/plain")

        def do_POST(self):
            # o token só existe na página servida aqui; o cabeçalho próprio força o navegador a perguntar antes
            # (preflight), e este servidor não responde a OPTIONS: página de outro site não consegue clicar
            if not self._host_ok() or self.headers.get("X-Token") != token or self.path != "/api/acao":
                return self._enviar(403, b"proibido", "text/plain")
            try:
                d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0") or 0)) or b"{}")
                r = acao(d)
            except Exception as e:  # o painel não pode cair por um botão
                r = {"ok": False, "erro": f"{type(e).__name__}: {e}"}
            self._enviar(200, json.dumps(r, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    return ThreadingHTTPServer(("127.0.0.1", porta), H)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="painel do Director")
    ap.add_argument("--porta", type=int, default=PORTA)
    ap.add_argument("--sem-abrir", action="store_true")
    a = ap.parse_args(argv)
    srv = servidor(a.porta, secrets.token_urlsafe(24))
    if not a.sem_abrir:
        threading.Timer(0.5, lambda: webbrowser.open(f"http://127.0.0.1:{a.porta}/")).start()
    if os.name == "nt":
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW("Director - Painel (deixe aberta no fundo)")  # type: ignore[attr-defined]
    print(f"Painel do Director: http://127.0.0.1:{a.porta}/", flush=True)
    print("Deixe esta janela aberta (pode ficar minimizada). Fechar a janela desliga o painel;", flush=True)
    print("ele volta sozinho no próximo atalho.", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
