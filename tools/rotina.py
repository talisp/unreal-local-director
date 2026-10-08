"""Os atalhos de dois cliques do operador (atalhos\\*.bat): roda uma linha, espera o fim, escreve um resultado CURTO
montado por programa (não texto livre do Qwen) em resultados\\ e abre o arquivo.

Uso (na raiz; os .bat já chamam assim):
  venv\\Scripts\\python.exe tools\\rotina.py junior      o júnior (hermes-dev, uns 10 a 20 min)
  venv\\Scripts\\python.exe tools\\rotina.py bateria     a bateria de testes do código (uns 5 min)
  venv\\Scripts\\python.exe tools\\rotina.py ensaio      o ensaio curto no Unreal: lança e espera acabar
  venv\\Scripts\\python.exe tools\\rotina.py noite       a noite no Unreal: lança e espera até a hora 'ate' da cena
  venv\\Scripts\\python.exe tools\\rotina.py astra       o Astra (Codex): pergunta, confirma a cota e envia
  venv\\Scripts\\python.exe tools\\rotina.py ver         como estão as 4 linhas agora (não roda nada)
  venv\\Scripts\\python.exe tools\\rotina.py escolher    mostra as variações da última rodada e grava a escolha do operador
  venv\\Scripts\\python.exe tools\\rotina.py painel      abre o painel no navegador (tools/painel.py)
Toda rotina liga o painel (se estiver desligado) e grava o começo e o fim em resultados/historico.jsonl, que o
painel mostra no histórico ao vivo. O resultado sempre tem, no topo, o veredito numa frase e "o que precisa de você". Os detalhes ficam em links.
"""
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "src"))
sys.path.insert(0, os.path.join(RAIZ, "tools"))
from unreal_macros import cena as C  # noqa: E402  # pyright: ignore[reportMissingImports]
from unreal_macros import fila as F  # noqa: E402  # pyright: ignore[reportMissingImports]
import director as D  # noqa: E402  # pyright: ignore[reportMissingImports]

RESULTADOS = os.path.join(RAIZ, "resultados")
PORTA_PAINEL = 8765
CENA_PADRAO = os.path.join(RAIZ, "cenas", "fila.md")
ESPERA_S = 60          # de quanto em quanto tempo a janela confere a rodada no Unreal
ENSAIO_MAX_MIN = 120   # o ensaio nunca prende a janela mais que isto
NOITE_FOLGA_MIN = 30   # depois da hora 'ate' da cena, espera no máximo isto


# ---------- utilidades ----------
def _agora() -> dt.datetime:
    return dt.datetime.now()


def _json(caminho: str):
    try:
        return json.load(open(caminho, encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _link(caminho: str) -> str:
    """Link relativo a partir de resultados/ (o arquivo que o operador abre)."""
    rel = os.path.relpath(caminho, RESULTADOS).replace("\\", "/")
    return f"[{os.path.relpath(caminho, RAIZ).replace(os.sep, '/')}](<{rel}>)"


def _mais_novo(padrao: str, desde: float = 0.0) -> str | None:
    xs = [x for x in glob.glob(os.path.join(RAIZ, padrao)) if os.path.getmtime(x) >= desde]
    return max(xs, key=os.path.getmtime) if xs else None


def _pid_vivo(pid) -> bool:
    if not pid:
        return False
    try:
        r = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"], capture_output=True, text=True, timeout=30,
                           creationflags=SEM_JANELA)
    except (OSError, ValueError, subprocess.SubprocessError):
        return True  # na dúvida, continua esperando (o prazo máximo segura)
    return str(int(pid)) in r.stdout


def gravar_resultado(nome: str, texto: str, quando: dt.datetime | None = None, pasta: str = RESULTADOS) -> str:
    os.makedirs(pasta, exist_ok=True)
    arq = os.path.join(pasta, f"{(quando or _agora()):%Y-%m-%d %Hh%M} - {nome}.md")
    open(arq, "w", encoding="utf-8", newline="\n").write(texto)
    return arq


def registrar(linha: str, texto: str, arquivo: str | None = None, pasta: str = RESULTADOS) -> None:
    """Uma linha no histórico que o painel mostra ao vivo."""
    os.makedirs(pasta, exist_ok=True)
    d = {"quando": _agora().isoformat(timespec="seconds"), "linha": linha, "texto": texto,
         "arquivo": os.path.relpath(arquivo, RAIZ).replace("\\", "/") if arquivo else None}
    with open(os.path.join(pasta, "historico.jsonl"), "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")


def painel_no_ar(porta: int = PORTA_PAINEL) -> bool:
    import socket
    try:
        socket.create_connection(("127.0.0.1", porta), timeout=1).close()
        return True
    except OSError:
        return False


NOVA_JANELA = 0x00000010   # CREATE_NEW_CONSOLE
SEM_JANELA = 0x08000000    # CREATE_NO_WINDOW: comando auxiliar (tasklist, git) nunca abre janela


def comando_painel() -> list:
    return [os.path.join(RAIZ, "venv", "Scripts", "python.exe"), os.path.join(RAIZ, "tools", "painel.py"), "--sem-abrir"]


def janela_minimizada():
    si = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
    si.wShowWindow = 7  # SW_SHOWMINNOACTIVE: minimizada e sem tirar o foco de onde o operador digita
    return si


def garantir_painel(abrir_navegador: bool = True) -> None:
    """Liga o painel se estiver desligado e abre no navegador. O painel ganha UMA janela própria, que abre
    minimizada e sem roubar o foco, e fica aberta (o operador a deixa no fundo). Sem janela (pythonw), cada comando
    que o painel chama abria uma janela preta que piscava e roubava o teclado (Talis, 08/10)."""
    if not painel_no_ar():
        # sem stdin/stdout aqui: senão o painel escreve na janela de quem o chamou, não na dele
        subprocess.Popen(comando_painel(), cwd=RAIZ, creationflags=NOVA_JANELA, startupinfo=janela_minimizada())
        for _ in range(20):
            if painel_no_ar():
                break
            time.sleep(0.5)
    if abrir_navegador:
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{PORTA_PAINEL}/")


def abrir(caminho: str) -> None:
    try:
        os.startfile(caminho)  # type: ignore[attr-defined]  # o programa padrão do Windows para .md
    except OSError:
        subprocess.Popen(["notepad.exe", caminho])


def _cabecalho(titulo: str, ok: bool | None, frase: str, precisa: list) -> list:
    icone = "✅" if ok else "⚠️" if ok is None else "❌"
    linhas = [f"# {titulo} · {_agora():%d/%m %H:%M}", "", f"## {icone} {frase}", "", "**O que precisa de você:**"]
    linhas += [f"- {p}" for p in precisa] if precisa else ["- nada."]
    return linhas + [""]


def _rodar(linha: str, args: list) -> int:
    print(f"\n--- rodando: {linha} {' '.join(args)} ---\n", flush=True)
    return D.rodar(linha, args)


# ---------- júnior ----------
def md_junior(r: dict | None, codigo: int, minutos: float) -> str:
    if not r:
        return "\n".join(_cabecalho("Júnior", False, f"o júnior não terminou (código {codigo}, {minutos} min)",
                                    ["chamar o Claude e mostrar este arquivo."]))
    ideias = r.get("ideias") or []
    problemas = [f"escreveu fora de ideias/: `{p}`" for p in r["auditoria"]["escritas_fora"]]
    problemas += [f"tentou usar o Unreal: `{u}`" for u in r["auditoria"]["unreal"]]
    problemas += [f"conferidor: {m}" for m in (r.get("conferidor") or {}).get("motivos", [])]
    precisa = [f"ler as {len(ideias)} ideias e dizer ao Claude quais aprovar."] if ideias else []
    if problemas:
        precisa.append("mostrar os problemas abaixo ao Claude.")
    frase = (f"{len(ideias)} ideias sobre \"{r['tema']['tema']}\" ({r['minutos']} min)" if r["ok"] else
             f"o júnior terminou com problema ({r['minutos']} min)")
    linhas = _cabecalho("Júnior", r["ok"], frase, precisa)
    linhas += ["## As ideias", ""]
    linhas += [f"{n}. {titulo}{'' if ok else ' (reprovada pelo conferidor)'}" for n, titulo, ok in ideias] or ["(nenhuma)"]
    linhas += ["", f"Texto completo: {_link(os.path.join(RAIZ, r['arquivo']))}", ""]
    if problemas:
        linhas += ["## Problemas", ""] + [f"- {p}" for p in problemas] + [""]
    return "\n".join(linhas)


def rotina_junior() -> str:
    t0 = time.time()
    print("Júnior: o Qwen (hermes-dev) pesquisa um tema e escreve ideias. Leva uns 10 a 20 minutos.")
    print("Pode deixar esta janela aberta; no fim o resultado abre sozinho.", flush=True)
    codigo = _rodar("junior", [])
    arq = _mais_novo(os.path.join("work", "junior", "*", "resumo.json"), t0)
    return gravar_resultado("junior", md_junior(_json(arq) if arq else None, codigo, round((time.time() - t0) / 60, 1)))


# ---------- bateria ----------
def md_bateria(r: dict | None, codigo: int) -> str:
    if not r:
        return "\n".join(_cabecalho("Bateria", False, f"a bateria não terminou (código {codigo})",
                                    ["chamar o Claude e mostrar este arquivo."]))
    falhas = [e for e in r["etapas"] if not e["ok"]]
    pend = [c for c in r["conhecidos"] if c.get("decisao_talis") == "pendente"]
    precisa = ["chamar o Claude e dizer: \"a bateria falhou, veja o resultado\"."] if falhas else []
    if pend:
        precisa.append(f"decidir {len(pend)} defeito(s) conhecido(s) pendente(s) (o Claude explica).")
    frase = (f"todo o código passou ({len(r['etapas'])} etapas, {round(r['duracao_s'] / 60, 1)} min)" if r["ok"] else
             f"{len(falhas)} de {len(r['etapas'])} etapas falharam")
    linhas = _cabecalho("Bateria", r["ok"], frase, precisa)
    if falhas:
        linhas += ["## O que falhou", ""] + [f"- **{e['nome']}**: {e.get('detalhe_curto', '')}" for e in falhas] + [""]
    linhas += ["## Etapas", "", "| Etapa | Resultado |", "|---|---|"]
    linhas += [f"| {e['nome']} | {'ok' if e['ok'] else 'FALHOU'} |" for e in r["etapas"]]
    linhas += ["", f"Commit testado: `{r['commit']}` · marco {'aprovado' if r['marco_aprovado'] else 'não aprovado'}", ""]
    return "\n".join(linhas)


def rotina_bateria() -> str:
    print("Bateria: testa o código inteiro numa cópia (sem Unreal). Leva uns 5 minutos.", flush=True)
    codigo = _rodar("bateria", [])
    head = D._git("rev-parse", "--short=12", "HEAD")
    return gravar_resultado("bateria", md_bateria(_json(os.path.join(RAIZ, "work", "bateria", head, "RESUMO.json")), codigo))


# ---------- Unreal (ensaio e noite) ----------
def ler_tentativas(pasta: str) -> list:
    out = []
    arq = os.path.join(pasta, "tentativas.jsonl")
    if os.path.exists(arq):
        for ln in open(arq, encoding="utf-8", errors="replace"):
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            if d.get("tipo_linha") == "tentativa":
                out.append(d)
    return out


def progresso(pasta: str) -> dict:
    tent = ler_tentativas(pasta)
    notas = [t["nota"] for t in tent if isinstance(t.get("nota"), (int, float))]
    return {"tentativas": len(tent), "melhor": min(notas) if notas else None, "sucesso": F.sucesso(tent)}


def rodada_acabou(pasta: str, lanc: dict, agora: dt.datetime, prazo: dt.datetime, vivo=_pid_vivo) -> str | None:
    """Por que a rodada acabou (frase), ou None se ainda está rodando."""
    if os.path.exists(os.path.join(pasta, "FECHAMENTO.md")):
        return "o Productor escreveu o fechamento"
    if lanc.get("modo") == "ensaio" and os.path.exists(os.path.join(pasta, "ENSAIO.md")):
        return "o Productor escreveu o relatório do ensaio"
    if not vivo(lanc.get("vigia_pid")) and not vivo(lanc.get("sessao_pid")):
        return "a vigia e o Productor pararam"
    if agora >= prazo:
        return "passou do horário-limite"
    return None


def prazo_da_rodada(lanc: dict, ate: str) -> dt.datetime:
    inicio = dt.datetime.fromisoformat(lanc["quando"])
    if lanc.get("modo") == "ensaio":
        return inicio + dt.timedelta(minutes=ENSAIO_MAX_MIN)
    h, m = map(int, ate.split(":"))
    fim = inicio.replace(hour=h, minute=m, second=0, microsecond=0)
    if fim <= inicio:
        fim += dt.timedelta(days=1)
    return fim + dt.timedelta(minutes=NOITE_FOLGA_MIN)


def _nota(x) -> str:
    return "—" if x is None else f"{x:g}"


def md_unreal(pasta: str, lanc: dict, motivo: str | None, variacoes_pedidas: int = 0) -> str:
    tent = ler_tentativas(pasta)
    validas = [t for t in tent if (t.get("avaliacao") or {}).get("valida")]
    p = progresso(pasta)
    titulo = f"Unreal · {lanc.get('modo', '?')} · cena {lanc.get('cena', '?')}"
    ev = C.estado_variacoes(validas, variacoes_pedidas) if variacoes_pedidas else None
    precisa = []
    if motivo is None:
        ok, frase = None, f"ainda rodando: {p['tentativas']} tentativas, melhor nota {_nota(p['melhor'])}"
    elif p["sucesso"]:
        ok = True
        frase = f"conseguiu: a mesma receita passou {p['sucesso']['vezes']} vezes com nota 0 ({p['tentativas']} tentativas)"
        if ev and ev["aceitas"]:
            precisa.append("ver os vídeos abaixo e escolher a melhor (no painel, botão \"escolher esta\").")
    else:
        ok, frase = False, f"não conseguiu: {p['tentativas']} tentativas, melhor nota {_nota(p['melhor'])} (0 = perfeita)"
    if motivo and lanc.get("modo") == "ensaio":
        precisa.append("se o ensaio foi bem, lançar a noite (dois cliques em \"Unreal NOITE\"); se não, chamar o Claude.")
    elif motivo and not p["sucesso"]:
        precisa.append("chamar o Claude para olhar o que travou.")
    linhas = _cabecalho(titulo, ok, frase, precisa)
    inicio = lanc.get("quando", "?")
    linhas += [f"Começou {inicio.replace('T', ' ')[:16]}" + (f" · terminou porque {motivo}" if motivo else ""), ""]
    if ev:
        linhas += ["## Variações", ""]
        if ev["base"] is None:
            linhas += ["Ainda não teve sucesso, então não há variações.", ""]
        else:
            linhas += ["| Opção | Tentativa | Vídeo |", "|---|---|---|"]
            for opcao, n in [("base", ev["base"])] + [(str(i + 1), n) for i, n in enumerate(ev["aceitas"])]:
                v = os.path.join(pasta, "videos", f"t{n:03d}.mp4")
                linhas.append(f"| {opcao} | {n} | {_link(v) if os.path.exists(v) else 'sem vídeo'} |")
            linhas += ["", f"Faltam {ev['faltam']} de {variacoes_pedidas} variações." if ev["faltam"] else
                       "As variações pedidas ficaram prontas.", ""]
    if tent:
        linhas += ["## Últimas tentativas", "", "| N | Nota | Clipes | Válida |", "|---|---|---|---|"]
        for t in tent[-8:]:
            clipes = " → ".join(x.get("clipe", "?") for x in t.get("receita") or [])
            linhas.append(f"| {t.get('n')} | {_nota(t.get('nota'))} | {clipes} | "
                          f"{'sim' if (t.get('avaliacao') or {}).get('valida') else 'não'} |")
        linhas.append("")
    detalhes = [os.path.join(pasta, x) for x in ("FECHAMENTO.md", "ENSAIO.md") if os.path.exists(os.path.join(pasta, x))]
    if detalhes:
        linhas += ["Detalhes (escritos pelo Qwen, só se quiser): " + " · ".join(_link(x) for x in detalhes), ""]
    return "\n".join(linhas)


def esperar_rodada(pasta: str, lanc: dict, prazo: dt.datetime, espera_s: int = ESPERA_S) -> str:
    ultimo = None
    while True:
        motivo = rodada_acabou(pasta, lanc, _agora(), prazo)
        p = progresso(pasta)
        linha = f"{p['tentativas']} tentativas · melhor nota {_nota(p['melhor'])}" + (" · SUCESSO" if p["sucesso"] else "")
        if linha != ultimo:
            print(f"{_agora():%H:%M} · {linha}", flush=True)
            ultimo = linha
        if motivo:
            return motivo
        time.sleep(espera_s)


def rotina_unreal(modo: str, arq_cena: str = CENA_PADRAO) -> str | None:
    cena = C.ler_cena(arq_cena)
    if modo == "ensaio":
        print("ENSAIO no Unreal: umas poucas tentativas para provar que tudo funciona (até 2 horas).")
    else:
        print(f"NOITE no Unreal: o Productor trabalha sozinho até as {cena['ate']}. Deixe o Unreal e o Hermes abertos.")
    print("Esta janela mostra o progresso. Se fechar a janela, a rodada continua (o painel continua mostrando).")
    if not OPC["sim"]:  # pelo botão do painel, a confirmação já foi dada lá
        input("Aperte Enter para lançar (ou feche a janela para desistir): ")
    t0 = time.time()
    codigo = _rodar("unreal", [f"--{modo}", "--cena", os.path.relpath(arq_cena, RAIZ)])
    arq = _mais_novo(os.path.join("work", "*", "LANCAMENTO.json"), t0)
    if codigo != 0 or not arq:
        txt = "\n".join(_cabecalho(f"Unreal · {modo}", False, "não lançou", [
            "ver a mensagem na janela preta (Unreal fechado? modelo fora do ar? trava ocupada?) e tentar de novo, "
            "ou chamar o Claude."]))
        return gravar_resultado(f"unreal {modo}", txt)
    lanc = _json(arq) or {}
    pasta = os.path.dirname(arq)
    print(f"\nLançado. Esperando acabar (confere a cada {ESPERA_S} s):", flush=True)
    motivo = esperar_rodada(pasta, lanc, prazo_da_rodada(lanc, cena["ate"]))
    return gravar_resultado(f"unreal {modo}", md_unreal(pasta, lanc, motivo, cena.get("variacoes", 0)))


# ---------- Astra ----------
PERGUNTA_PADRAO = ("O que mudou desde a última revisão do Astra pode quebrar o Director, gastar o Unreal à toa ou "
                   "sujar a cena? Dê só os achados que conseguir provar com arquivo:linha.")


def md_astra(conf: dict | None, escalada: str | None, pergunta: str) -> str:
    if not conf:
        return "\n".join(_cabecalho("Astra", False, "o Astra não respondeu", ["chamar o Claude e mostrar este arquivo."]))
    n = len(conf["achados"])
    precisa = [f"dizer ao Claude: \"corrija os achados do Astra\" ({n})."] if n else []
    if not conf["ok"]:
        precisa.append("a resposta veio fora do formato: chamar o Claude.")
    linhas = _cabecalho("Astra", conf["ok"] and not n, f"{n} achado(s)" if n else "nenhum problema achado", precisa)
    linhas += [f"Pergunta: {pergunta}", ""]
    if n:
        linhas += ["| # | Gravidade | Achado |", "|---|---|---|"]
        linhas += [f"| {a['n']} | {a['gravidade']} | {a['achado']} |" for a in conf["achados"]]
        linhas.append("")
    if escalada:
        linhas += [f"Resposta completa: {_link(escalada)}", ""]
    return "\n".join(linhas)


def rotina_astra() -> str | None:
    print("Astra: o Codex revisa o código (só lê, não muda nada). GASTA COTA do Codex.")
    if OPC["sim"]:  # pelo botão do painel: a pergunta e o "sim" vieram de lá
        pergunta = (OPC["pergunta"] or "").strip() or PERGUNTA_PADRAO
        print(f"pergunta: {pergunta}")
    else:
        print("Escreva a pergunta e aperte Enter. Só Enter = revisar o que mudou desde a última revisão.")
        pergunta = input("pergunta: ").strip() or PERGUNTA_PADRAO
    if not OPC["sim"] and input("Enviar ao Astra? Digite s e Enter (qualquer outra coisa desiste): ").strip().lower() != "s":
        print("Desisti; nada foi enviado.")
        return None
    t0, tema = time.time(), f"talis-{_agora():%H%M}"
    codigo = _rodar("astra", ["--tema", tema, "--pergunta", pergunta, "--enviar", "--confirmo-cota"])
    resp = os.path.join(RAIZ, "work", "astra", f"{dt.date.today().isoformat()}-{tema}", "resposta.md")
    conf = None
    if os.path.exists(resp):
        import astra as A  # pyright: ignore[reportMissingImports]
        conf = A.conferir_resposta(open(resp, encoding="utf-8").read())
    escalada = _mais_novo(os.path.join("escaladas", f"*-ASTRA-{tema}.md"), t0)
    print(f"(astra saiu com {codigo})")
    return gravar_resultado("astra", md_astra(conf, escalada, pergunta))


# ---------- ver e escolher ----------
def md_ver() -> str:
    linhas = _cabecalho("Como está o Director", None, "situação de cada linha agora", [])
    linhas = linhas[:3] + ["| Linha | Situação |", "|---|---|"]
    linhas += [f"| {lin} | {txt} |" for lin, txt in D.estado()]
    linhas.append("")
    arq = _mais_novo(os.path.join("work", "*", "LANCAMENTO.json"))
    if arq:
        lanc = _json(arq) or {}
        pasta = os.path.dirname(arq)
        cena = C.ler_cena(CENA_PADRAO)
        motivo = rodada_acabou(pasta, lanc, _agora(), prazo_da_rodada(lanc, cena["ate"]))
        linhas += ["---", "", md_unreal(pasta, lanc, motivo, cena.get("variacoes", 0)).replace("\n# ", "\n## ", 1)]
    return "\n".join(linhas)


def rotina_escolher() -> str | None:
    import escolha as E  # pyright: ignore[reportMissingImports]
    arq = _mais_novo(os.path.join("work", "*", "LANCAMENTO.json"))
    if not arq:
        print("Ainda não houve rodada no Unreal.")
        return None
    pasta = os.path.dirname(arq)
    try:
        d = E.gerar(pasta, None, (_json(arq) or {}).get("cena"))
    except ValueError as e:
        print(f"Nada para escolher: {e}")
        return None
    print(f"Rodada {d['rodada']}. Opções:")
    for o in d["opcoes"]:
        print(f"  {o['opcao']:>4} · tentativa {o['n']} · vídeo: {o['video'] or 'sem vídeo'}")
    if os.path.isdir(os.path.join(pasta, "videos")):
        abrir(os.path.join(pasta, "videos"))
    x = input("Qual você escolhe? (base, ou o número; só Enter = escolher depois): ").strip()
    if not x:
        return None
    reg = E.escolher(pasta, x)
    txt = "\n".join(_cabecalho("Escolha", True, f"escolhida a opção {reg['opcao']} (tentativa {reg['tentativa']})", []) +
                    [f"Gravada na biblioteca: `{reg['id']}`", ""])
    return gravar_resultado("escolha", txt)


OPC = {"sim": False, "pergunta": None, "navegador": True}  # o botão do painel passa --sim, --pergunta, --sem-navegador
NOMES = {"junior": "júnior", "bateria": "bateria", "ensaio": "ensaio no Unreal", "noite": "noite no Unreal",
         "astra": "Astra", "escolher": "escolha da variação"}
ROTINAS = {"junior": rotina_junior, "bateria": rotina_bateria, "ensaio": lambda: rotina_unreal("ensaio"),
           "noite": lambda: rotina_unreal("noite"), "astra": rotina_astra,
           "ver": lambda: gravar_resultado("situacao", md_ver()), "escolher": rotina_escolher,
           "painel": lambda: garantir_painel() and None}


def main(argv) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    if not argv or argv[0] not in ROTINAS:
        print(__doc__)
        return 2
    nome = argv[0]
    OPC.update(sim="--sim" in argv, navegador="--sem-navegador" not in argv,
               pergunta=argv[argv.index("--pergunta") + 1] if "--pergunta" in argv[:-1] else None)
    if nome != "painel":
        try:
            garantir_painel(OPC["navegador"])
        except OSError as e:
            print(f"(o painel não abriu: {e}; a rotina continua)")
    if nome in NOMES:
        registrar(nome, f"começou: {NOMES[nome]}")
    try:
        arq = ROTINAS[nome]()
    except (EOFError, KeyboardInterrupt):
        print("\nInterrompido.")
        if nome in NOMES:
            registrar(nome, f"interrompido: {NOMES[nome]} (Ctrl+C)")
        return 1
    except Exception as e:  # a janela pode fechar sozinha: o erro fica no histórico e num resultado
        import traceback
        txt = "\n".join(_cabecalho(NOMES.get(nome, nome), False, f"deu erro: {type(e).__name__}",
                                   ["chamar o Claude e mostrar este arquivo."]) + ["```", traceback.format_exc(), "```", ""])
        arq = gravar_resultado(f"{nome} ERRO", txt)
        registrar(nome, f"ERRO: {NOMES.get(nome, nome)}: {type(e).__name__}: {e}"[:200], arq)
        abrir(arq)
        return 1
    if nome in NOMES:
        registrar(nome, f"terminou: {NOMES[nome]}" if arq else f"sem resultado: {NOMES[nome]} (desistiu ou nada a fazer)",
                  arq)
    if arq:
        print(f"\nResultado: {arq}")
        abrir(arq)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
