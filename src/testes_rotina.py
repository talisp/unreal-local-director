"""Testes dos atalhos de dois cliques (tools/rotina.py) e do painel (tools/painel.py), SEM rodar nenhuma linha de
verdade: nada é lançado, o Hermes e o Unreal não são chamados. O servidor do painel sobe numa porta livre."""
import datetime as dt
import importlib.util
import json
import os
import socket
import sys
import tempfile
import threading
import urllib.error
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(RAIZ, "tools"))
from testes_v003_bloco1 import caso, rodar  # noqa: E402


def _mod(nome):
    s = importlib.util.spec_from_file_location(nome, os.path.join(RAIZ, "tools", f"{nome}.py"))
    assert s and s.loader
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


RO, PA = _mod("rotina"), _mod("painel")
BASE = [{"clipe": "Sit_To_Stand", "papel": "levantar"}, {"clipe": "Victory", "papel": "acenar"},
        {"clipe": "Walking", "papel": "andar"}, {"clipe": "Stop_Walking_2", "papel": "parar"}]


def _t(n, nota, acenar="Victory", variacao=False, valida=True, quando="2026-10-08T21:00:00"):
    from unreal_macros import receita as R
    passos = [dict(p) for p in BASE]
    passos[1]["clipe"] = acenar
    return {"n": n, "tipo_linha": "tentativa", "receita": passos, "assinatura": R.assinatura({"passos": passos}),
            "nota": nota, "variacao": variacao, "avaliacao": {"valida": valida, "nota": nota}, "quando": quando}


def _rodada(tent, lanc=None, arquivos=()):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "tentativas.jsonl"), "w", encoding="utf-8") as f:
        for t in tent:
            f.write(json.dumps(t) + "\n")
        f.write('{"tipo_linha": "tentativa", "n": 99, "corta')  # linha cortada por queda: ignorada
    if lanc:
        json.dump(lanc, open(os.path.join(d, "LANCAMENTO.json"), "w", encoding="utf-8"))
    for a in arquivos:
        os.makedirs(os.path.dirname(os.path.join(d, a)), exist_ok=True)
        open(os.path.join(d, a), "w").write("x")
    return d


@caso("resumos curtos: veredito no topo e 'o que precisa de você'; sem dados vira falha, nunca 'ok'")
def t_resumos():
    jr = {"ok": True, "tema": {"n": 2, "tema": "trocas"}, "arquivo": "ideias/x.md", "minutos": 12.0,
          "auditoria": {"escritas_fora": [], "unreal": []}, "conferidor": {"motivos": []},
          "ideias": [[1, "Ideia A", True], [2, "Ideia B", False]]}
    m = RO.md_junior(jr, 0, 12.0)
    assert "✅ 2 ideias" in m and "**O que precisa de você:**" in m and "aprovar" in m and "reprovada" in m, m
    assert m.index("O que precisa") < m.index("## As ideias")
    ruim = dict(jr, ok=False, auditoria={"escritas_fora": ["docs/X.md"], "unreal": []})
    assert "❌" in RO.md_junior(ruim, 0, 1) and "docs/X.md" in RO.md_junior(ruim, 0, 1)
    assert "❌" in RO.md_junior(None, 1, 3.0) and "Claude" in RO.md_junior(None, 1, 3.0)
    bat = {"ok": False, "commit": "abc", "duracao_s": 300, "marco_aprovado": False, "conhecidos": [],
           "etapas": [{"nome": "ruff", "ok": True}, {"nome": "suite:testes_cena", "ok": False, "detalhe_curto": "9/10"}]}
    m = RO.md_bateria(bat, 1)
    assert "❌ 1 de 2 etapas falharam" in m and "suite:testes_cena**: 9/10" in m and "a bateria falhou" in m, m
    assert "✅" in RO.md_bateria(dict(bat, ok=True, etapas=bat["etapas"][:1]), 0)
    conf = {"ok": True, "achados": [{"n": 1, "gravidade": "alta", "achado": "furo"}]}
    assert "1 achado(s)" in RO.md_astra(conf, None, "p?") and "corrija" in RO.md_astra(conf, None, "p?")
    assert "nenhum problema" in RO.md_astra(dict(conf, achados=[]), None, "p?")


@caso("fim da rodada: fechamento, ENSAIO.md só no ensaio, vigia e Productor mortos, prazo; senão continua")
def t_acabou():
    vivo, morto = (lambda pid: True), (lambda pid: False)
    agora, prazo = dt.datetime(2026, 10, 9, 3, 0), dt.datetime(2026, 10, 9, 8, 30)
    d = _rodada([_t(1, 5.0)])
    assert RO.rodada_acabou(d, {"modo": "noite"}, agora, prazo, vivo) is None
    assert "pararam" in RO.rodada_acabou(d, {"modo": "noite"}, agora, prazo, morto)
    assert "horário" in RO.rodada_acabou(d, {"modo": "noite"}, prazo, prazo, vivo)
    e = _rodada([], arquivos=["ENSAIO.md"])
    assert RO.rodada_acabou(e, {"modo": "noite"}, agora, prazo, vivo) is None  # na noite, ENSAIO.md não fecha
    assert "ensaio" in RO.rodada_acabou(e, {"modo": "ensaio"}, agora, prazo, vivo)
    assert "fechamento" in RO.rodada_acabou(_rodada([], arquivos=["FECHAMENTO.md"]), {"modo": "noite"}, agora, prazo, vivo)
    noite = RO.prazo_da_rodada({"modo": "noite", "quando": "2026-10-08T20:00:00"}, "08:00")
    assert noite == dt.datetime(2026, 10, 9, 8, 30), noite
    assert RO.prazo_da_rodada({"modo": "noite", "quando": "2026-10-09T02:00:00"}, "08:00") == dt.datetime(2026, 10, 9, 8, 30)
    assert RO.prazo_da_rodada({"modo": "ensaio", "quando": "2026-10-08T15:00:00"}, "08:00") == dt.datetime(2026, 10, 8, 17, 0)


@caso("resumo do Unreal: sucesso + variações com link do vídeo e o pedido de escolher; sem sucesso = não conseguiu")
def t_md_unreal():
    tent = [_t(1, 4.0), _t(2, 0.0), _t(3, 0.0), _t(4, 0.0), _t(5, 0.0, "Waving_2", True), _t(6, None, valida=False)]
    d = _rodada(tent, arquivos=["videos/t005.mp4", "FECHAMENTO.md"])
    m = RO.md_unreal(d, {"modo": "noite", "cena": "fila", "quando": "2026-10-08T20:00:00"}, "o Productor escreveu o fechamento", 3)
    assert "✅ conseguiu" in m and "6 tentativas" in m and "escolher esta" in m, m
    assert "t005.mp4" in m and "| base | 2 | sem vídeo |" in m and "Faltam 2 de 3" in m, m
    assert "FECHAMENTO.md" in m and m.index("O que precisa") < m.index("## Variações")
    m2 = RO.md_unreal(_rodada([_t(1, 7.5), _t(2, 3.25)]), {"modo": "noite"}, "passou do horário-limite", 3)
    assert "❌ não conseguiu" in m2 and "melhor nota 3.25" in m2 and "chamar o Claude" in m2, m2
    m3 = RO.md_unreal(_rodada([_t(1, 2.0)]), {"modo": "ensaio"}, "o Productor escreveu o relatório do ensaio", 3)
    assert "lançar a noite" in m3, m3
    assert "⚠️ ainda rodando" in RO.md_unreal(_rodada([_t(1, 2.0)]), {"modo": "noite"}, None, 3)


@caso("histórico e resultado: a linha entra no historico.jsonl; o .md tem data e nome; o painel junta as fontes")
def t_historico():
    with tempfile.TemporaryDirectory() as tmp:
        res = os.path.join(tmp, "resultados")
        arq = RO.gravar_resultado("junior", "# x\n", dt.datetime(2026, 10, 8, 21, 5), res)
        assert os.path.basename(arq) == "2026-10-08 21h05 - junior.md"
        RO.registrar("junior", "começou: júnior", None, res)
        RO.registrar("junior", "terminou: júnior", arq, res)
        linhas = [json.loads(x) for x in open(os.path.join(res, "historico.jsonl"), encoding="utf-8")]
        assert [x["texto"] for x in linhas] == ["começou: júnior", "terminou: júnior"] and linhas[1]["arquivo"]
        rod = os.path.join(tmp, "work", "fila_x")
        os.makedirs(rod)
        with open(os.path.join(rod, "tentativas.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps(_t(1, 4.0, quando="2026-10-08T21:01:00")) + "\n")
            f.write(json.dumps(_t(2, None, valida=False, quando="2026-10-08T21:09:00")) + "\n")
        open(os.path.join(rod, "FECHAMENTO.md"), "w").write("fim")
        h = PA.historico(tmp, rod)
        textos = [e["texto"] for e in h]
        assert any("tentativa 1: nota 4.0" in t for t in textos) and any("tentativa 2: nota inválida" in t for t in textos)
        assert any("FECHAMENTO.md" in t for t in textos) and any("começou: júnior" in t for t in textos), textos
        assert [e["quando"] for e in h] == sorted((e["quando"] for e in h), reverse=True)
        assert PA.rodada_atual(tmp) == rod


@caso("ideias no painel: lê problema, ideia e custo; a decisão do operador aparece; botão com decisão estranha é recusado")
def t_ideias():
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "ideias"))
        open(os.path.join(tmp, "ideias", "2026-10-08-x.md"), "w", encoding="utf-8").write(
            "# Ideias\n\n## 1. Primeira\n- **Problema:** P1\n- **Ideia:** I1\n- **Custo:** baixo\n\n"
            "## 2. Segunda\n- **Problema:** P2\n- **Ideia:** I2\n- **Custo:** alto\n")
        open(os.path.join(tmp, "ideias", "decisoes.jsonl"), "w", encoding="utf-8").write(
            json.dumps({"arquivo": "ideias/2026-10-08-x.md", "n": 2, "decisao": "recusada", "quando": "2026-10-08T22:00:00"}) + "\n")
        ii = PA.ler_ideias(tmp)
        assert [(i["n"], i["problema"], i["custo"], i["decisao"]) for i in ii] == [(1, "P1", "baixo", None), (2, "P2", "alto", "recusada")], ii
        falta = PA.pendencias_do_talis(None, ii, False, tmp)
        assert any("1 ideia" in f["texto"] for f in falta) and any("bateria falhou" in f["texto"] for f in falta)
        assert any("ensaio" in f["texto"] for f in falta)
    assert not PA.acao({"acao": "ideia", "decisao": "talvez"})["ok"]
    assert not PA.acao({"acao": "abrir", "arquivo": "../../Windows/win.ini"})["ok"]
    assert not PA.acao({"acao": "abrir", "arquivo": "docs/TALIS.md"})["ok"]  # fora da lista do painel
    assert not PA.acao({"acao": "formatar"})["ok"]


@caso("servidor do painel: página e dados respondem; botão sem token ou com outro Host é barrado; vídeo só de work/*/videos")
def t_servidor():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    srv = PA.servidor(porta, "tok123")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{porta}"

    def pedir(caminho, corpo=None, cab=None):
        r = urllib.request.Request(base + caminho, data=corpo, headers=cab or {}, method="POST" if corpo else "GET")
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
    try:
        cod, pag = pedir("/")
        assert cod == 200 and b'"tok123"' in pag and b"{{TOKEN}}" not in pag
        cod, dados = pedir("/api/dados")
        d = json.loads(dados)
        assert cod == 200 and {"rodando", "unreal", "ideias", "historico", "resultados", "falta_voce"} <= set(d), list(d)
        corpo = json.dumps({"acao": "parar_vigia"}).encode()
        assert pedir("/api/acao", corpo)[0] == 403  # sem token: nada acontece
        assert pedir("/api/acao", corpo, {"X-Token": "errado"})[0] == 403
        assert pedir("/api/acao", corpo, {"X-Token": "tok123", "Host": "malicioso.com"})[0] == 403
        assert pedir("/", None, {"Host": "malicioso.com"})[0] == 403
        assert pedir("/video?p=docs/TALIS.md")[0] == 404 and pedir("/video?p=work/x/videos/../../docs/TALIS.md")[0] == 404
        ok = json.loads(pedir("/api/acao", json.dumps({"acao": "ideia", "decisao": "talvez"}).encode(),
                              {"X-Token": "tok123", "Content-Type": "application/json"})[1])
        assert ok == {"ok": False, "erro": "decisão inválida"}, ok
    finally:
        srv.shutdown()
        srv.server_close()


@caso("atalhos .bat: cada um chama uma rotina que existe, na pasta certa, com quebra de linha do Windows")
def t_atalhos():
    pasta = os.path.join(RAIZ, "atalhos")
    bats = [b for b in os.listdir(pasta) if b.endswith(".bat")]
    assert len(bats) == 6, bats
    for b in bats:
        bruto = open(os.path.join(pasta, b), "rb").read()
        assert b"\r\n" in bruto and b"\n" not in bruto.replace(b"\r\n", b""), f"{b}: quebra de linha"
        texto = bruto.decode("ascii")
        pasta_cd = texto.split('cd /d "', 1)[1].split('"', 1)[0]  # a pasta fixa de instalação (não a da bateria)
        assert os.path.exists(os.path.join(pasta_cd, "tools", "rotina.py")), (b, pasta_cd)
        cmd = texto.split("tools\\rotina.py ", 1)[1].split()[0]
        assert cmd in RO.ROTINAS, (b, cmd)
    assert {t.split("tools\\rotina.py ", 1)[1].split()[0] for t in
            (open(os.path.join(pasta, b), encoding="ascii").read() for b in bats)} == \
        {"junior", "bateria", "ensaio", "noite", "astra", "painel"}


@caso("nenhuma janela piscando (Talis 08/10): o painel abre UMA janela minimizada sem foco; comando auxiliar sem janela")
def t_sem_piscar():
    import ast
    import subprocess
    chamadas = []
    no_ar, popen = RO.painel_no_ar, RO.subprocess.Popen
    setattr(RO, "painel_no_ar", lambda porta=0: len(chamadas) > 0)
    setattr(RO.subprocess, "Popen", lambda cmd, **k: chamadas.append((cmd, k)))
    try:
        RO.garantir_painel(abrir_navegador=False)
    finally:
        setattr(RO, "painel_no_ar", no_ar)
        setattr(RO.subprocess, "Popen", popen)
    cmd, k = chamadas[0]
    assert cmd[0].endswith("python.exe") and not cmd[0].endswith("pythonw.exe"), cmd  # pythonw = sem janela = pisca
    assert k["creationflags"] == 0x10 and k["startupinfo"].wShowWindow == 7, k  # nova janela, minimizada, sem foco
    assert k["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert not {"stdin", "stdout", "stderr"} & set(k), k  # a saída vai para a janela do painel, não para a do atalho
    # todo comando auxiliar (git, tasklist) que o painel ou a espera chamam roda sem janela
    for arq in ("painel.py", "rotina.py"):
        arvore = ast.parse(open(os.path.join(RAIZ, "tools", arq), encoding="utf-8").read())
        for n in ast.walk(arvore):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "run" and \
                    getattr(n.func.value, "id", "") == "subprocess":
                assert any(kw.arg == "creationflags" for kw in n.keywords), f"{arq}:{n.lineno} sem creationflags"


@caso("botões de rodar: rotina desconhecida recusada; já rodando (atalho ou Unreal) bloqueia; um Unreal por vez")
def t_botoes():
    assert not PA.rodar_rotina("formatar_disco")["ok"]
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "resultados"))
        agora = dt.datetime(2026, 10, 8, 22, 0)
        with open(os.path.join(tmp, "resultados", "historico.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"quando": "2026-10-08T21:50:00", "linha": "junior", "texto": "começou: júnior"}) + "\n")
            f.write(json.dumps({"quando": "2026-10-08T21:00:00", "linha": "bateria", "texto": "começou: bateria"}) + "\n")
            f.write(json.dumps({"quando": "2026-10-08T21:55:00", "linha": "astra", "texto": "começou: Astra"}) + "\n")
            f.write(json.dumps({"quando": "2026-10-08T21:58:00", "linha": "astra", "texto": "terminou: Astra"}) + "\n")
        assert PA.ocupadas(False, tmp, agora) == ["junior"]  # bateria velha demais; Astra terminou
        assert PA.ocupadas(True, tmp, agora) == ["ensaio", "junior", "noite"]


if __name__ == "__main__":
    sys.exit(0 if rodar([t_resumos, t_acabou, t_md_unreal, t_historico, t_ideias, t_servidor, t_atalhos, t_sem_piscar,
                         t_botoes],
                        "rotina") else 1)
