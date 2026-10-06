"""Bloco 5 — seções 4 a 8 (trava, experimentos, detector real, banco/fila/supervisor/rotação, falhas provocadas).
python bloco5_unreal_b.py <secao>. Usa os registros REAIS gerados no Unreal pelas seções anteriores."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bloco5_unreal as B  # noqa: E402
from bloco5_unreal import M, SB_TESTE, SRC, V002, PROD, registra, salvar, checar_parcial, cena_teste  # noqa: E402
from unreal_macros import diario, direcao as D, emperramento as E, experimentos as X, resolver as RS  # noqa: E402
from unreal_macros import rotacao as R, sessao as SS, supervisor as S, trava as T  # noqa: E402

PY = sys.executable
EXP = os.path.join(V002, "work", "experimentos")
RODADA = time.strftime("%H%M")  # nomes únicos por rodada (repetir a seção não colide com experimentos antigos)
REL = os.path.join(V002, "work", "relatorios")
SUP = os.path.join(V002, "work", "supervisor")


def _sb_commit(arquivos: dict, msg: str):
    for rel, txt in arquivos.items():
        open(os.path.join(SB_TESTE, rel), "w", encoding="utf-8").write(txt)
    subprocess.run(["git", "-C", SB_TESTE, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "add", "-A"], check=True)
    if subprocess.run(["git", "-C", SB_TESTE, "diff", "--cached", "--quiet"]).returncode:  # só commita se houver mudança
        subprocess.run(["git", "-C", SB_TESTE, "-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com", "commit", "-qm", msg], check=True)


# ---------- 4a: trava com processos reais + concorrência ----------
def s4_trava():
    tmp = tempfile.mkdtemp()
    p, log = os.path.join(tmp, "t.trava"), os.path.join(tmp, "t.log")
    cod = f"import sys; sys.path.insert(0, {SRC!r}); from unreal_macros import trava; trava.pegar({p!r}, 'x')"
    viva = subprocess.Popen([PY, "-c", cod + "; import time; time.sleep(60)"])
    for _ in range(100):
        if os.path.exists(p):
            break
        time.sleep(0.1)
    d = T.liberar_orfa(p, log)
    registra("trava com dono vivo: liberação recusada", False, d["liberada"], d["liberada"] is False)
    viva.kill()
    viva.wait()
    d = T.liberar_orfa(p, log)
    registra("dono morto (processo real encerrado): liberar_trava_orfa libera", True, d["liberada"], d["liberada"])
    outro = subprocess.Popen([PY, "-c", "import time; time.sleep(30)"])
    time.sleep(0.3)
    json.dump({"pid": outro.pid, "inicio": time.time() - 9999, "host": __import__("socket").gethostname()}, open(p, "w"))
    st = T.estado(p)
    registra("PID reaproveitado (processo real, horário de criação forjado)", "morta", st["estado"], st["estado"] == "morta")
    json.dump({"pid": outro.pid, "inicio": None, "host": __import__("socket").gethostname(), "desde": 0}, open(p, "w"))
    json.dump({"pid": outro.pid, "macro": "v001", "desde": time.time() - 10 * 3600}, open(p, "w"))
    st = T.estado(p)
    registra("formato antigo + idade 10 h com pid vivo: conservador (viva)", "viva", st["estado"], st["estado"] == "viva")
    outro.kill()
    os.remove(p)
    corrida = os.path.join(tmp, "c.trava")
    cod = (f"import sys, time; sys.path.insert(0, {SRC!r}); from unreal_macros import trava\n"
           f"try:\n    trava.pegar({corrida!r}, 'c'); print('GANHEI'); time.sleep(4)\nexcept Exception as e: print('PERDI')")
    procs = [subprocess.Popen([PY, "-c", cod], stdout=subprocess.PIPE, text=True) for _ in range(6)]
    saidas = [pr.communicate()[0].strip() for pr in procs]
    registra("concorrência: 6 processos ao mesmo tempo -> exatamente 1 operador", 1, saidas.count("GANHEI"), saidas.count("GANHEI") == 1, saidas)
    salvar("s4_trava")


# ---------- 4b: experimento real no sandbox de teste ----------
SMOKE = '''"""Bloco 5: corrida real inofensiva no sandbox de teste (zona x=20000, só bonecos TESTE_)."""
import testes_contrato as TC
from unreal_macros import macros as M
TC.limpar()
TC.c.call(TC.SCENE, "add_to_scene_from_asset", asset_path="/Engine/BasicShapes/Cube.Cube", name="TESTE_PISO",
          xform=TC.xform(TC.ZX, 0, -50, s=(12, 12, 1)))
TC.boneco("TESTE_BONECO_A", TC.ZX, 0)
M.importar_clipe("Head_Nod_Yes")
r = M.aplicar_clipe("TESTE_BONECO_A", "Head_Nod_Yes", loop=True)
m = M.medir_personagem("TESTE_BONECO_A", com_vizinhos=False)
print("relatorio_id:", r["id"]); print("relatorio_id:", m["id"])
print("codigo:", M._ambiente()["codigo"], "versao:", M.versao_codigo())
ok = r["ok"] and m["ok"]
TC.limpar(); M.limpar_estudio()
print(f"{int(ok) + 1}/2 testes ok")
'''


def s4_experimento():
    _sb_commit({"src/b5_smoke.py": SMOKE, "src/b5_rapido.py": "print('1/1 testes ok')\n",
                "src/b5_falha.py": "print('0/1 testes ok')\nraise SystemExit(1)\n"}, "bloco 5: scripts de corrida")
    e = X.iniciar("b5-smoke", "experimento", "corrida real inofensiva do bloco 5 no sandbox de teste",
                  hipoteses=[{"descricao": "macros do sandbox de teste medem igual à v0.0.2", "mudanca": "nenhuma: só medir no sandbox",
                              "previsao": "Head_Nod_Yes ok e medida ok"},
                             {"descricao": "estúdio do sandbox em x=20000 interfere com a cena", "mudanca": "verificar zona isolada do estúdio",
                              "previsao": "sem interferência"}], sandbox=SB_TESTE, pedido="P15")
    registra("worktree do experimento criado do master do sandbox de teste", f"{SB_TESTE}-exp", os.path.dirname(e["worktree"]),
             os.path.dirname(e["worktree"]) == f"{SB_TESTE}-exp")
    c = X.rodar("b5-smoke", "src/b5_smoke.py")
    saida = open(c["log"], encoding="utf-8").read()
    registra("corrida real: código usado é o do worktree (sandbox de teste), nunca a produção", "worktree",
             [l for l in saida.splitlines() if l.startswith("codigo:")], e["worktree"] in saida and PROD + "\\src" not in saida)
    registra("corrida real: resultado da ferramenta", "2/2 e saída 0", (c["testes_ok"], c["codigo_saida"]),
             c["testes_ok"] == [2, 2] and c["codigo_saida"] == 0, saida[-600:])
    registra("corrida real: relatório real associado (ids)", "2 ids", c["relatorio_ids"], len(c["relatorio_ids"]) == 2)
    fechado = X.fechar("b5-smoke", "smoke real ok")
    out = subprocess.run([PY, "-c", f"import sys; sys.path.insert(0,{SRC!r}); from unreal_macros import experimentos as X; "
                          f"print(X.carregar('b5-smoke')['estado'])"], capture_output=True, text=True).stdout.strip()
    registra("segundo processo lê o estado persistido", "fechado", out, out == "fechado")
    X.iniciar("b5-limite", "experimento", "recusa real segura: terceira corrida",
              hipoteses=[{"descricao": "corrida rapida sem unreal para medir limite", "mudanca": "script b5_rapido sem efeito",
                          "previsao": "terceira recusada"},
                         {"descricao": "controle de tempo e corridas do controlador", "mudanca": "nenhuma alteração de código",
                          "previsao": "estado persistido"}], sandbox=SB_TESTE, pedido=D.TRANSVERSAL)
    X.rodar("b5-limite", "src/b5_rapido.py")
    X.rodar("b5-limite", "src/b5_rapido.py")
    try:
        X.rodar("b5-limite", "src/b5_rapido.py")
        registra("recusa real: terceira corrida", "recusa", "rodou", False)
    except X.Recusa as r:
        registra("recusa real: terceira corrida", "recusa", str(r)[:60], "limite" in str(r))
    try:
        X.iniciar("b5-dep", "experimento", "dependência não integrada (branch do Hermes no remoto)",
                  hipoteses=[{"descricao": "x" * 12, "mudanca": "y" * 12, "previsao": "zzzzz"},
                             {"descricao": "a b c d e f g h", "mudanca": "k l m n o p q r", "previsao": "wwwww"}],
                  dependencias=["origin/exp/captura-estavel"], sandbox=SB_TESTE)
        registra("recusa real: dependência não integrada (exp5 do Hermes)", "recusa", "aceitou", False)
    except X.Recusa as r:
        registra("recusa real: dependência não integrada (exp5 do Hermes)", "recusa", str(r)[:70], "integrada" in str(r))
    sha = __import__("hashlib").sha256
    g = subprocess.run(["git", "-C", SB_TESTE, "show", "master:src/unreal_macros/guarda.py"], capture_output=True, text=True, encoding="utf-8").stdout
    base = json.load(open(os.path.join(V002, "work", "bloco5_ambientes.json")))["sha_guarda"]
    registra("guarda do sandbox de teste intacta (master)", base, sha(g.encode()).hexdigest(), sha(g.encode()).hexdigest() == base)
    salvar("s4_experimento")


# ---------- 5: detector com resultados reais ----------
def s5_detector():
    cena_teste()
    M.importar_clipe("Walking")
    M.importar_clipe("Head_Nod_Yes")
    ctx = {"linha": "b5-real"}
    r1 = M.aplicar_clipe("TESTE_BONECO_0", "Walking", loop=True, contexto=ctx)
    checar_parcial(r1)
    r2 = M.aplicar_clipe("TESTE_BONECO_0", "Walking", loop=True, contexto=ctx)
    checar_parcial(r2)
    itens = E.carregar_historico(REL, EXP)
    est = E.avaliar(itens, "b5-real")
    d = est["ultimo_disparo"] or {}
    registra("2 tentativas reais equivalentes -> repetição, degrau cutucar", ("repeticao", "cutucar"), (d.get("tipo"), est["degrau"]),
             d.get("tipo") == "repeticao" and est["degrau"] == "cutucar", {"evidencia": d.get("evidencia"), "erro": d.get("erro")})
    E.registrar_disparos(est, os.path.join(V002, "work", "emperramento", "disparos.jsonl"))
    o = RS.orientar(est)
    registra("resolver recebe o estado calculado e indica lições/contorno", "tipo + lições", (o.get("tipo_falha"), [l["id"] for l in o.get("licoes", [])]),
             o.get("degrau") == "cutucar" and o.get("licoes"))
    lic = (o.get("licoes") or [{"id": "L-ver-01"}])[0]["id"]
    RS.registrar_uso_licao(lic, "b5-real")
    time.sleep(1.1)
    r3 = M.aplicar_clipe("TESTE_BONECO_0", "Head_Nod_Yes", loop=True, contexto=ctx)
    checar_parcial(r3)
    itens = E.carregar_historico(REL, EXP)
    est2 = E.avaliar(itens, "b5-real")
    registra("resultado real melhor -> progresso, escada zerada", ("progresso", None), (est2["progressos"], est2["degrau"]),
             est2["progressos"] >= 1 and est2["degrau"] is None and r3["ok"])
    v = RS.atualizar_votos(itens).get(lic, {})
    registra(f"voto da lição {lic} atualizado pelo evento", "+1", v, v.get("positivos", 0) >= 1)
    trava_v002 = M.TRAVA
    cod = f"import sys; sys.path.insert(0, {SRC!r}); from unreal_macros import trava; trava.pegar({trava_v002!r}, 'outro operador'); import time; time.sleep(40)"
    dono = subprocess.Popen([PY, "-c", cod])
    for _ in range(100):
        if os.path.exists(trava_v002):
            break
        time.sleep(0.1)
    try:
        esp = [M.medir_personagem("TESTE_BONECO_0", com_vizinhos=False, contexto={"linha": "b5-espera"}) for _ in range(3)]
    finally:
        dono.kill()
        dono.wait()
        T.liberar_orfa(trava_v002, os.path.join(V002, "work", "trava.log"))
    est3 = E.avaliar(E.carregar_historico(REL, EXP), "b5-espera")
    registra("espera real (trava de outro operador vivo) não é emperramento", "0 disparos, 3 esperas",
             (len(est3["disparos"]), est3["esperas"]), not est3["disparos"] and est3["esperas"] == 3,
             [e.get("espera") for e in esp])
    salvar("s5_detector")


# ---------- 6: banco, fila, supervisor (laço), rotação ----------
def s6_bloco4():
    import supervisor_laco as SL
    cena_teste()
    for pid, esperado in (("P01", "atendivel"), ("P14", "parcial"), ("P09", "nao_atendivel")):
        registra(f"mapa: {pid}", esperado, D.atendibilidade(pid)["situacao"], D.atendibilidade(pid)["situacao"] == esperado)
    M.importar_clipe("Waving")
    w = M.aplicar_clipe("TESTE_BONECO_1", "Waving", loop=True)
    registra("P01 'acena' é atendível de verdade (Waving em boneco de teste)", True, w["ok"], w["ok"], w["bloqueio"])
    f = M.capturar_evidencia("TESTE_BONECO_1", vista="frontal", nome="B5 P14")
    linhas_info = {"ok": f["ok"], "bloqueio": f["bloqueio"]}
    B.linhas.append({"teste": "P14 'foto' (parcial): resultado real na zona de teste (informativo)", "observado": linhas_info, "ok": True})
    conh = D.resultados_conhecidos()
    exp_caso = {"id": "E-walk", "tipo": "exploracao", "macro": "aplicar_clipe", "args": ["TESTE_BONECO_0", "Walking"], "kwargs": {"loop": True}}
    reg_caso = {"id": "C-med", "tipo": "contrato", "macro": "aplicar_clipe", "args": ["TESTE_BONECO_1", "Waving"], "kwargs": {"loop": True}}
    fila = D.montar_fila([exp_caso, reg_caso], M.versao_codigo(), conh)
    registra("fila real: exploração exclui caso já respondido (Walking real)", "E-walk excluído", [c["id"] for c in fila["excluidos"]],
             [c["id"] for c in fila["excluidos"]] == ["E-walk"])
    registra("fila real: contrato em dia nesta versão", "C-med em dia", [c["id"] for c in fila["contrato_em_dia"]], [c["id"] for c in fila["contrato_em_dia"]] == ["C-med"])
    fila2 = D.montar_fila([reg_caso], "versao-futura", conh)
    registra("fila real: código mudou -> contrato volta como regressão", "regressao", [c.get("motivo") for c in fila2["fila"]], [c.get("motivo") for c in fila2["fila"]] == ["regressao"])
    rc = SL.laco(0.5, vezes=3, pasta=SUP, trava_path=os.path.join(V002, "work", "nenhuma.trava"))
    log = [json.loads(l) for l in open(os.path.join(SUP, "laco.log"), encoding="utf-8")]
    aval = [l for l in log if l["evento"] == "avaliacao"][-3:]
    registra("laço do supervisor: 3 execuções reais registradas, sem alarme com progresso recente (A)", "3 / sem alarme",
             (len(aval), [a["alarmes"] for a in aval]), rc == 0 and len(aval) == 3 and not any(a["alarmes"] for a in aval))
    agora = time.time()
    rB = S.avaliar(agora + 46 * 60, trava_path=os.path.join(V002, "work", "nenhuma.trava"), registrar=False)
    registra("relógio +46 min sem progresso -> alarme (B)", "atividade_sem_progresso ou sem_atividade",
             [a["tipo"] for a in rB["alarmes"]], {"atividade_sem_progresso", "sem_atividade"} & {a["tipo"] for a in rB["alarmes"]})
    th = threading.Thread(target=X.rodar, args=(f"b5-espera-sup-{RODADA}", "src/b5_lento.py"))
    _sb_commit({"src/b5_lento.py": "import time\ntime.sleep(15)\nprint('1/1 testes ok')\n"}, "bloco 5: corrida lenta")
    X.iniciar(f"b5-espera-sup-{RODADA}", "experimento", "espera legítima para o supervisor",
              hipoteses=[{"descricao": "corrida longa declarada pelo controlador", "mudanca": "script lento sem efeito",
                          "previsao": "supervisor não alarma"},
                         {"descricao": "relógio do supervisor descontando espera", "mudanca": "nenhuma alteração de código",
                          "previsao": "esperas ativas listadas"}], sandbox=SB_TESTE, pedido=D.TRANSVERSAL)
    th.start()
    time.sleep(4)
    rC = S.avaliar(time.time() + 20 * 60, trava_path=os.path.join(V002, "work", "nenhuma.trava"), registrar=False)
    th.join()
    registra("espera legítima (corrida real em andamento) -> sem alarme (C)", "sem alarme de progresso",
             ([a["tipo"] for a in rC["alarmes"]], [e["tipo"] for e in rC["esperas_ativas"]]),
             not {"atividade_sem_progresso", "sem_atividade"} & {a["tipo"] for a in rC["alarmes"]} and any(e["tipo"] == "corrida" for e in rC["esperas_ativas"]))
    copia = tempfile.mkdtemp()
    shutil.copytree(os.path.join(PROD, "src"), os.path.join(copia, "src"))
    shutil.copytree(os.path.join(PROD, "docs"), os.path.join(copia, "docs"))
    hashes = os.path.join(copia, "hashes.txt")
    open(hashes, "w").write("".join(l for l in open(os.path.join(PROD, "work", "hashes_producao_0610b.txt")) if l.split()[1].startswith(("src/", "docs/"))))
    open(os.path.join(copia, "src", "paridade.py"), "a").write("\n# alterado no teste do bloco 5\n")
    rD = S.avaliar(time.time(), trava_path=os.path.join(V002, "work", "nenhuma.trava"), hashes_producao=hashes, base_producao=copia)
    pausou = M.pausa_ativa()
    med = M.medir_personagem("TESTE_BONECO_1", com_vizinhos=False)
    registra("produção ALTERADA (cópia controlada) -> alarme + PAUSA + macro recusa (D)", "producao_alterada, PAUSA, recusa",
             ([a["tipo"] for a in rD["alarmes"]], bool(pausou), med["bloqueio"]),
             "producao_alterada" in [a["tipo"] for a in rD["alarmes"]] and pausou and "PAUSADO" in (med["bloqueio"] or ""))
    os.remove(os.path.join(SUP, "PAUSA"))  # ação do OPERADOR (o laço nunca remove)
    B.linhas.append({"teste": "PAUSA removida pelo operador (Claude) depois do teste D", "ok": True})
    os.makedirs(os.path.join(V002, "work", "bancada_hermes"), exist_ok=True)
    antes = S.avaliar(time.time() + 46 * 60, trava_path=os.path.join(V002, "work", "nenhuma.trava"), registrar=False)["ultimo_progresso"]
    open(os.path.join(V002, "work", "bancada_hermes", "diario.jsonl"), "a", encoding="utf-8").write('{"nota": "progredi muito!"}\n')
    depois = S.avaliar(time.time() + 46 * 60, trava_path=os.path.join(V002, "work", "nenhuma.trava"), registrar=False)["ultimo_progresso"]
    registra("texto 'progredi' ignorado (E)", "último progresso igual", depois == antes, depois == antes)
    for nome in (f"b5-nome-a-{RODADA}", f"b5-nome-b-{RODADA}"):
        X.iniciar(nome, "experimento", "mesma estratégia com outro nome",
                  hipoteses=[{"descricao": "estrategia repetida sob nome novo", "mudanca": "script b5_falha sem efeito",
                              "previsao": "sessão percebe"},
                             {"descricao": "controle de nomes no supervisor", "mudanca": "nenhuma alteração de código",
                              "previsao": "alarme de sessão"}], sandbox=SB_TESTE, pedido=D.TRANSVERSAL)
        X.rodar(nome, "src/b5_falha.py")
    rF = S.avaliar(time.time(), trava_path=os.path.join(V002, "work", "nenhuma.trava"), registrar=False)
    sess = [a for a in rF["alarmes"] if a["tipo"] == "emperramento_de_sessao"]
    registra("mesma estratégia com nomes diferentes -> emperramento de sessão (F)", "b5-nome-a + b5-nome-b (desta rodada)",
             sess[0]["linhas"] if sess else None, bool(sess) and {f"b5-nome-a-{RODADA}", f"b5-nome-b-{RODADA}"} <= set(sess[0]["linhas"]))
    p = SS.passagem(trava_path=os.path.join(V002, "work", "nenhuma.trava"))
    registra("passagem de sessão sobre o estado real (<= 4 KB)", "<= 4000", len(json.dumps(p, default=str)), len(json.dumps(p, default=str)) <= 4000)
    salvar("s6_bloco4")


def s6_rotacao():
    tmp = tempfile.mkdtemp()
    rel, exp, lic = os.path.join(tmp, "relatorios"), os.path.join(tmp, "experimentos"), os.path.join(tmp, "licoes")
    shutil.copytree(REL, rel)
    shutil.copytree(EXP, exp)
    if os.path.exists(os.path.join(V002, "work", "licoes")):
        shutil.copytree(os.path.join(V002, "work", "licoes"), lic)
    itens = E.carregar_historico(rel, exp)
    linhas_ = sorted({t.get("linha") for t in itens if t.get("linha")})
    antes = {l: (E.avaliar(itens, l)["emperrado"], E.avaliar(itens, l)["degrau"]) for l in linhas_}
    votos_antes = RS.atualizar_votos(itens, lic) if os.path.exists(lic) else {}
    n = len(os.listdir(rel))
    r = R.arquivar(time.time() + 8 * 86400, pasta_rel=rel, pasta_exp=exp, pasta_arquivo=os.path.join(tmp, "arq"), pasta_licoes=lic)
    itens2 = E.carregar_historico(rel, exp)
    depois = {l: (E.avaliar(itens2, l)["emperrado"], E.avaliar(itens2, l)["degrau"]) for l in linhas_}
    registra("rotação (cópia dos dados reais): arquivou e nada sumiu", n, len(os.listdir(rel)) + len(r["arquivados"]),
             len(os.listdir(rel)) + len(r["arquivados"]) == n, {"arquivados": len(r["arquivados"]), "protegidos": len(r["protegidos"])})
    registra("rotação: estado do detector igual em todas as linhas reais", antes, depois, antes == depois)
    if os.path.exists(lic):
        registra("rotação: votos iguais", votos_antes, RS.atualizar_votos(itens2, lic), RS.atualizar_votos(itens2, lic) == votos_antes)
    orig = diario.PASTA_RELATORIOS
    diario.PASTA_RELATORIOS = rel
    try:
        ok = all(diario.carregar_relatorio(i)["id"] == i for i in r["arquivados"][:20])
    finally:
        diario.PASTA_RELATORIOS = orig
    registra("rotação: relatórios arquivados relidos do arquivo morto", True, ok, ok)
    conh = D.resultados_conhecidos(rel, os.path.join(tmp, "arq", "indice.jsonl"))
    registra("rotação: regressão rastreável (índice conta resultados)", ">= arquivados", sum(len(v) for v in conh.values()),
             sum(len(v) for v in conh.values()) >= len(r["arquivados"]))
    salvar("s6_rotacao")


# ---------- 7: falhas provocadas ----------
def s7_falhas():
    _sb_commit({"src/b5_longo.py": "import time\ntime.sleep(60)\nprint('1/1 testes ok')\n"}, "bloco 5: corrida longa")
    X.iniciar(f"b5-interrompida-{RODADA}", "experimento", "corrida interrompida no meio (processo morto)",
              hipoteses=[{"descricao": "interromper o processo da corrida", "mudanca": "matar o processo do controlador",
                          "previsao": "não vira sucesso"},
                         {"descricao": "estado depois de reiniciar o processo", "mudanca": "nenhuma alteração de código",
                          "previsao": "estado legível"}], sandbox=SB_TESTE, pedido=D.TRANSVERSAL)
    cod = f"import sys; sys.path.insert(0, {SRC!r}); from unreal_macros import experimentos as X; X.rodar('b5-interrompida-{RODADA}', 'src/b5_longo.py')"
    pr = subprocess.Popen([PY, "-X", "utf8", "-c", cod])
    time.sleep(5)
    subprocess.run(["taskkill", "/PID", str(pr.pid), "/T", "/F"], capture_output=True)
    e = X.carregar(f"b5-interrompida-{RODADA}")
    registra("corrida interrompida não vira sucesso (sem corrida registrada)", "0 corridas", len(e["corridas"]), len(e["corridas"]) == 0)
    r30 = S.avaliar(time.time() + 30 * 60, trava_path=os.path.join(V002, "work", "nenhuma.trava"), registrar=False)
    perdida = [a for a in r30["alarmes"] if a["tipo"] == "corrida_perdida" and f"b5-interrompida-{RODADA}" in str(a["evidencia"])]
    aberta = [x for x in r30["esperas_ativas"] if x.get("linha") == f"b5-interrompida-{RODADA}"]
    registra("corrida interrompida há 30 min (> teto de 25): supervisor NÃO pode seguir tratando como espera", "alarme corrida_perdida",
             ([a["tipo"] for a in r30["alarmes"]], aberta), bool(perdida) and not aberta)
    est = os.path.join(EXP, "b5-corrompido.json")
    open(est, "w").write("{lixo")
    try:
        X.rodar("b5-corrompido", "src/b5_rapido.py")
        registra("estado de experimento corrompido não vira sucesso", "erro", "rodou", False)
    except Exception as ex:  # noqa: BLE001
        registra("estado de experimento corrompido não vira sucesso", "erro explícito", type(ex).__name__, True)
    os.remove(est)
    try:
        diario.carregar_relatorio("20991231-000000-1-1")
        registra("relatório ausente -> recusa", "FileNotFoundError", "carregou", False)
    except FileNotFoundError:
        registra("relatório ausente -> recusa", "FileNotFoundError", "FileNotFoundError", True)
    salvar("s7_falhas")




# ---------- 6a: atividade normal real numa pasta limpa + fila na versão atual ----------
def s6a_normal():
    import supervisor_laco as SL
    limpa = tempfile.mkdtemp(prefix="b5_normal_")
    orig = M.RAIZ_WORK
    M.RAIZ_WORK = limpa
    try:
        cena_teste()
        for clipe in ("Head_Nod_Yes", "Waving"):
            M.importar_clipe(clipe)
        rels = [M.aplicar_clipe("TESTE_BONECO_0", "Head_Nod_Yes", loop=True),
                M.medir_personagem("TESTE_BONECO_0", com_vizinhos=False),
                M.aplicar_clipe("TESTE_BONECO_1", "Waving", loop=True)]
    finally:
        M.RAIZ_WORK = orig
    for r in rels:
        checar_parcial(r)
    kw = dict(pasta_rel=os.path.join(limpa, "relatorios"), pasta_exp=os.path.join(limpa, "experimentos"),
              trava_path=os.path.join(limpa, "nenhuma.trava"))
    rc = SL.laco(0.5, vezes=3, pasta=os.path.join(limpa, "supervisor"), **kw)
    log = [json.loads(l) for l in open(os.path.join(limpa, "supervisor", "laco.log"), encoding="utf-8")]
    aval = [l for l in log if l["evento"] == "avaliacao"]
    registra("laço do supervisor em sessão real NORMAL (pasta limpa): 3 execuções, sem alarme (A)", "3 / sem alarme",
             (len(aval), [a["alarmes"] for a in aval], [r["ok"] for r in rels]),
             rc == 0 and len(aval) == 3 and not any(a["alarmes"] for a in aval) and all(r["ok"] for r in rels))
    conh = D.resultados_conhecidos()
    atual = {"id": "E-wave", "tipo": "exploracao", "macro": "aplicar_clipe", "args": ["TESTE_BONECO_1", "Waving"], "kwargs": {"loop": True}}
    velho = {"id": "E-walk", "tipo": "exploracao", "macro": "aplicar_clipe", "args": ["TESTE_BONECO_0", "Walking"], "kwargs": {"loop": True}}
    fila = D.montar_fila([atual, velho], M.versao_codigo(), conh)
    registra("fila real: caso respondido NESTA versão é excluído (Waving da seção 6)", "E-wave excluído",
             [c["id"] for c in fila["excluidos"]], [c["id"] for c in fila["excluidos"]] == ["E-wave"])
    nota = [c.get("nota") for c in fila["fila"] if c["id"] == "E-walk"]
    registra("fila real: resultado de versão ANTIGA do código volta como informação nova (Walking)", "código mudou",
             nota, nota and "código mudou" in nota[0])
    salvar("s6a_normal")

if __name__ == "__main__":
    {"s4t": s4_trava, "s4e": s4_experimento, "s5": s5_detector, "s6": s6_bloco4, "s6r": s6_rotacao, "s7": s7_falhas,
     "s6a": lambda: s6a_normal()}[sys.argv[1]]()
