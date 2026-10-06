"""v0.0.2 Bloco 2 — testes SEM o Unreal: trava verificável (processos reais) e controlador de experimentos
(repositório git falso que simula o sandbox, em pasta temporária; o sandbox real não é tocado)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
PROD_SRC = os.environ.get("ULD_PROD_SRC", os.path.join(os.path.expanduser("~"), "unreal-macros", "src"))
sys.path.insert(0, AQUI)
from unreal_macros import experimentos as X  # noqa: E402
from unreal_macros import trava as T  # noqa: E402

resultados = []
TMP = tempfile.mkdtemp(prefix="uld_b2_")


def caso(nome):
    def deco(fn):
        def rodar():
            try:
                fn()
                resultados.append((nome, True, ""))
            except Exception as e:  # noqa: BLE001
                resultados.append((nome, False, f"{type(e).__name__}: {e}"))
        return rodar
    return deco


def _recusa(fn, *a, contem="", **k):
    try:
        fn(*a, **k)
    except X.Recusa as e:
        assert contem.lower() in str(e).lower(), f"recusou, mas pelo motivo errado: {e}"
        return str(e)
    raise AssertionError("deveria ter recusado")


# ---------- trava ----------
TOMA_E_SAI = "import sys; sys.path.insert(0, {aqui!r}); from unreal_macros import trava; trava.pegar({p!r}, 'teste')"
TOMA_E_DORME = TOMA_E_SAI + "; import time; time.sleep(60)"


def _trava_de(codigo: str, p: str, esperar=True):
    proc = subprocess.Popen([sys.executable, "-c", codigo.format(aqui=AQUI, p=p)])
    if esperar:
        proc.wait(timeout=30)
    else:
        for _ in range(100):
            if os.path.exists(p):
                break
            time.sleep(0.1)
    return proc


@caso("trava órfã CONFIRMADA (dono saiu sem soltar) é liberada e a decisão registrada")
def t_orfa():
    p, log = os.path.join(TMP, "orfa.trava"), os.path.join(TMP, "trava.log")
    _trava_de(TOMA_E_SAI, p)
    assert T.estado(p)["estado"] == "morta"
    d = T.liberar_orfa(p, log)
    assert d["liberada"] and not os.path.exists(p), d
    assert "liberar_trava_orfa" in open(log, encoding="utf-8").read()


@caso("trava com dono VIVO é recusada (liberar e pegar)")
def t_viva():
    p, log = os.path.join(TMP, "viva.trava"), os.path.join(TMP, "trava.log")
    proc = _trava_de(TOMA_E_DORME, p, esperar=False)
    try:
        d = T.liberar_orfa(p, log)
        assert not d["liberada"] and d["estado"] == "viva" and os.path.exists(p), d
        try:
            T.pegar(p, "outro")
            raise AssertionError("pegou trava de dono vivo")
        except RuntimeError as e:
            assert "ocupado" in str(e)
    finally:
        proc.kill()


@caso("idade sozinha NÃO libera: trava de 10 h com dono vivo continua presa")
def t_idade():
    p, log = os.path.join(TMP, "velha.trava"), os.path.join(TMP, "trava.log")
    proc = _trava_de(TOMA_E_DORME, p, esperar=False)
    try:
        info = json.load(open(p, encoding="utf-8"))
        info["desde"] = time.time() - 10 * 3600
        json.dump(info, open(p, "w", encoding="utf-8"))
        assert not T.liberar_orfa(p, log)["liberada"]
    finally:
        proc.kill()


@caso("pid REAPROVEITADO (mesmo número, outro horário de criação) = dono morto")
def t_pid_reusado():
    p = os.path.join(TMP, "reuso.trava")
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        time.sleep(0.5)
        json.dump({"pid": proc.pid, "inicio": time.time() - 99999, "host": __import__("socket").gethostname()}, open(p, "w"))
        st = T.estado(p)
        assert st["estado"] == "morta" and "reaproveitado" in st["motivo"], st
    finally:
        proc.kill()


@caso("trava antiga (v0.0.1, sem horário de criação): pid vivo = viva; pid inexistente = morta")
def t_formato_antigo():
    p = os.path.join(TMP, "antiga.trava")
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        time.sleep(0.3)
        json.dump({"pid": proc.pid, "macro": "x", "desde": 0}, open(p, "w"))
        assert T.estado(p)["estado"] == "viva"
    finally:
        proc.kill()
    proc.wait()
    json.dump({"pid": proc.pid, "macro": "x", "desde": 0}, open(p, "w"))
    assert T.estado(p)["estado"] == "morta"


@caso("trava CORROMPIDA não é tratada como órfã em silêncio (só com confirmação explícita)")
def t_corrompida():
    p, log = os.path.join(TMP, "lixo.trava"), os.path.join(TMP, "trava.log")
    open(p, "w").write("{lixo")
    assert T.estado(p)["estado"] == "corrompida"
    assert not T.liberar_orfa(p, log)["liberada"] and os.path.exists(p)
    try:
        T.pegar(p, "x")
        raise AssertionError("pegou trava corrompida")
    except RuntimeError as e:
        assert "corrompida" in str(e)
    assert T.liberar_orfa(p, log, corrompida=True)["liberada"] and not os.path.exists(p)


# ---------- sandbox falso ----------
SB = os.path.join(TMP, "sb")
EST = os.path.join(TMP, "estado")


def _g(*a, cwd=None):
    subprocess.run(["git", *a], cwd=cwd or SB, check=True, capture_output=True)


def _montar_sandbox():
    os.makedirs(os.path.join(SB, "src", "unreal_macros"))
    arqs = {
        "src/unreal_macros/__init__.py": "",
        "src/unreal_macros/guarda.py": "# GUARDA — nao editar\n",
        "src/ok.py": "print('22/22 testes ok, 10 chamadas ao Unreal')\nprint('relatorio_id: 20261006-120000-1-1')\n",
        "src/falha.py": "print('20/22 testes ok')\nraise SystemExit(1)\n",
        "src/lento.py": "import time\ntime.sleep(8)\n",
        "src/sonda.py": ("import json, os, sys\nimport unreal_macros\n"
                         "print('SONDA ' + json.dumps({'pacote': unreal_macros.__file__, 'path': sys.path,"
                         " 'trava_env': [k for k in os.environ if 'TRAVA' in k.upper()] or None}))\n"),
        "src/proibido.py": "URL = 'http://127.0.0.1:8001/mcp'\n",
        "evidencia.txt": "log que comprova a causa\n",
    }
    for rel, txt in arqs.items():
        open(os.path.join(SB, rel), "w", encoding="utf-8").write(txt)
    _g("init", "-q", "-b", "master")
    _g("-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    _g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
    _g("checkout", "-q", "-b", "exp/integrada")
    open(os.path.join(SB, "src", "a.py"), "w").write("x = 1\n")
    _g("-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    _g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "integrada")
    _g("checkout", "-q", "master")
    _g("-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-ff", "exp/integrada", "-m", "integra")
    _g("checkout", "-q", "-b", "exp/solta")
    open(os.path.join(SB, "src", "b.py"), "w").write("y = 2\n")
    _g("-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    _g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "solta")
    _g("checkout", "-q", "master")


H_A = {"descricao": "medir a deriva pelo centro da regiao das pernas",
       "mudanca": "workflows._gate_deriva usa a mascara das pernas", "previsao": "Talking_2 deriva < 15"}
H_B = {"descricao": "aumentar a tolerancia do gate de deriva para gestos amplos",
       "mudanca": "tol de 15 para 25 cm em plateia_em_loop", "previsao": "Walking ainda reprova"}
H_A_REFORMULADA = {"descricao": "a deriva passa a ser medida pelo centro das pernas",
                   "mudanca": "_gate_deriva passa a usar a mascara de pernas", "previsao": "Talking_2 passa"}


def _novo(nome, **k):
    base = dict(tipo="experimento", objetivo="corrigir falso-FAIL de deriva em gestos parados",
                hipoteses=[H_A, H_B], sandbox=SB, pasta=EST)
    base.update(k)
    return X.iniciar(nome, **base)


@caso("experimento válido cria cópia própria a partir do master e guarda a alternativa não escolhida")
def t_iniciar_ok():
    e = _novo("exp-ok")
    assert os.path.isdir(e["worktree"]) and e["branch"] == "exp/exp-ok"
    alts = [json.loads(l) for l in open(os.path.join(EST, "alternativas.jsonl"), encoding="utf-8")]
    assert any(a["experimento"] == "exp-ok" and a["situacao"] == "nao_testada" and a["indice"] == 1 for a in alts)


@caso("terceira corrida é recusada")
def t_terceira():
    _novo("exp-tres")
    X.rodar("exp-tres", "src/ok.py", pasta=EST)
    X.rodar("exp-tres", "src/ok.py", pasta=EST)
    _recusa(X.rodar, "exp-tres", "src/ok.py", pasta=EST, contem="limite de 2 corridas")


@caso("corrida depois de 60 min é recusada")
def t_prazo():
    e = _novo("exp-prazo")
    _recusa(X.rodar, "exp-prazo", "src/ok.py", pasta=EST, agora=e["inicio"] + 60 * 60 + 1, contem="prazo")


@caso("corrida que estoura o tempo é cortada e marcada (não fica pendurada)")
def t_estouro():
    _novo("exp-lento")
    orig = X.MAX_CORRIDA_S
    X.MAX_CORRIDA_S = 2
    try:
        c = X.rodar("exp-lento", "src/lento.py", pasta=EST)
    finally:
        X.MAX_CORRIDA_S = orig
    assert c["estourou_tempo"] and c["codigo_saida"] is None and c["segundos"] < 6, c


@caso("dependência inexistente e dependência NÃO integrada são recusadas; integrada é aceita")
def t_dependencias():
    _recusa(_novo, "exp-dep1", dependencias=["exp/nao-existe"], contem="não existe")
    _recusa(_novo, "exp-dep2", dependencias=["exp/solta"], contem="não está integrada")
    assert _novo("exp-dep3", dependencias=["exp/integrada"])["dependencias"] == ["exp/integrada"]


@caso("experimento sem hipóteses suficientes (0, 1 ou campos vazios) é recusado")
def t_hipoteses_insuf():
    _recusa(_novo, "exp-h0", hipoteses=None, contem="2 ou 3")
    _recusa(_novo, "exp-h1", hipoteses=[H_A], contem="2 ou 3")
    _recusa(_novo, "exp-h4", hipoteses=[H_A, H_B, H_B, H_A], contem="2 ou 3")
    _recusa(_novo, "exp-hv", hipoteses=[H_A, dict(H_B, mudanca="")], contem="mudanca")


@caso("hipótese reformulada é recusada (determinístico); hipóteses distintas passam; limiar documentado")
def t_duplicada():
    s_dup, s_dist = X.similaridade(H_A, H_A_REFORMULADA), X.similaridade(H_A, H_B)
    assert s_dup >= X.LIMIAR_DUPLICATA > s_dist, (s_dup, s_dist)
    _recusa(_novo, "exp-dup", hipoteses=[H_A, H_A_REFORMULADA], contem="reformulada")


@caso("causa comprovada segue caminho de CONSERTO (sem hipóteses); conserto sem evidência ou com hipóteses é recusado")
def t_conserto():
    e = X.iniciar("conserto-ok", "conserto", "corrigir import do numpy no servidor", causa_evidencia="evidencia.txt",
                  correcao="carregar numpy na partida com OPENBLAS_NUM_THREADS=1", sandbox=SB, pasta=EST)
    assert e["tipo"] == "conserto" and e["hipoteses"] == [] and os.path.isdir(e["worktree"])
    _recusa(X.iniciar, "conserto-sem-ev", "conserto", "corrigir algo comprovado", correcao="trocar X por Y diretamente",
            causa_evidencia="nao-existe.txt", sandbox=SB, pasta=EST, contem="evidência")
    _recusa(X.iniciar, "conserto-hip", "conserto", "corrigir algo comprovado", hipoteses=[H_A, H_B],
            correcao="trocar X por Y diretamente", causa_evidencia="evidencia.txt", sandbox=SB, pasta=EST, contem="não leva hipóteses")


@caso("aposta sem meta ou sem prazo é recusada; aposta válida limita o prazo do experimento")
def t_aposta():
    sem_meta = dict(H_B, aposta={"prazo_min": 30, "criterio_encerramento": "encerrar se nao abrir capacidade"})
    _recusa(_novo, "aposta-sm", hipoteses=[H_A, sem_meta], contem="meta verificável")
    sem_prazo = dict(H_B, aposta={"meta": {"metrica": "pedidos_atendidos", "comparador": ">=", "valor": 1},
                                  "criterio_encerramento": "encerrar se nao abrir capacidade"})
    _recusa(_novo, "aposta-sp", hipoteses=[H_A, sem_prazo], contem="prazo")
    boa = dict(H_B, aposta={"meta": {"metrica": "pedidos_atendidos", "comparador": ">=", "valor": 1}, "prazo_min": 20,
                            "criterio_encerramento": "encerrar se a metrica nao subir em 2 corridas"})
    e = _novo("aposta-ok", hipoteses=[H_A, boa], escolhida=1)
    assert e["limite_min"] == 20


@caso("estado persiste entre processos (iniciar, rodar e fechar em sessões separadas)")
def t_persistencia():
    cod = ("import sys; sys.path.insert(0, {aqui!r}); from unreal_macros import experimentos as X; import json; {acao}")
    passos = [
        "X.iniciar('exp-proc', 'experimento', 'objetivo longo o bastante', hipoteses=" + repr([H_A, H_B]) +
        f", sandbox={SB!r}, pasta={EST!r})",
        f"X.rodar('exp-proc', 'src/ok.py', pasta={EST!r})",
        f"X.fechar('exp-proc', 'acho que ajudou', pasta={EST!r})",
    ]
    for acao in passos:
        r = subprocess.run([sys.executable, "-X", "utf8", "-c", cod.format(aqui=AQUI, acao=acao)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-600:]
    e = X.carregar("exp-proc", EST)
    assert e["estado"] == "fechado" and len(e["corridas"]) == 1 and e["resultado"]["ultima_testes_ok"] == [22, 22]
    assert e["corridas"][0]["relatorio_ids"] == ["20261006-120000-1-1"]
    assert e["interpretacao_declarada"] == "acho que ajudou"


@caso("fechar exige corrida; resultado vem da ferramenta (falha medida), não do texto do agente")
def t_fechar():
    _novo("exp-fecha")
    _recusa(X.fechar, "exp-fecha", "deu tudo certo", pasta=EST, contem="ao menos 1 corrida")
    X.rodar("exp-fecha", "src/falha.py", pasta=EST)
    e = X.fechar("exp-fecha", "deu tudo certo", pasta=EST)
    assert e["resultado"]["ultima_codigo_saida"] == 1 and e["resultado"]["ultima_testes_ok"] == [20, 22]
    _recusa(X.rodar, "exp-fecha", "src/ok.py", pasta=EST, contem="fechado")


@caso("guarda: cópia com guarda.py ALTERADA não roda")
def t_guarda_alterada():
    e = _novo("exp-guarda")
    with open(os.path.join(e["worktree"], "src", "unreal_macros", "guarda.py"), "a") as f:
        f.write("def checar(*a, **k): return None\n")
    _recusa(X.rodar, "exp-guarda", "src/ok.py", pasta=EST, contem="ALTERADA")


@caso("guarda: script fora da cópia, inexistente ou apontando para produção/MCP bruto é recusado")
def t_guarda_script():
    _novo("exp-script")
    _recusa(X.rodar, "exp-script", "../../sb/src/ok.py", pasta=EST, contem="fora da cópia")
    _recusa(X.rodar, "exp-script", "src/nao_existe.py", pasta=EST, contem="fora da cópia")
    _recusa(X.rodar, "exp-script", "src/proibido.py", pasta=EST, contem="proibido")


@caso("guarda: a corrida usa o pacote do SANDBOX (cópia do experimento), nunca o da produção, e sem trava trocada")
def t_guarda_ambiente():
    e = _novo("exp-sonda")
    os.environ["UNREAL_MACROS_TRAVA"] = os.path.join(TMP, "desvio.trava")
    try:
        c = X.rodar("exp-sonda", "src/sonda.py", pasta=EST)
    finally:
        os.environ.pop("UNREAL_MACROS_TRAVA", None)
    saida = open(c["log"], encoding="utf-8").read()
    sonda = json.loads([l for l in saida.splitlines() if l.startswith("SONDA ")][0][6:])
    wt = os.path.realpath(e["worktree"])
    assert os.path.realpath(sonda["pacote"]).startswith(wt), sonda["pacote"]
    assert not any(os.path.realpath(p) == os.path.realpath(PROD_SRC) for p in sonda["path"] if p)
    assert sonda["trava_env"] is None


@caso("toda recusa fica registrada em eventos.jsonl (histórico para o bloco 3)")
def t_eventos():
    evs = [json.loads(l) for l in open(os.path.join(EST, "eventos.jsonl"), encoding="utf-8")]
    tipos = {e["evento"] for e in evs}
    assert {"iniciado", "corrida", "recusa", "fechado"} <= tipos, tipos
    assert sum(e["evento"] == "recusa" for e in evs) >= 10


if __name__ == "__main__":
    _montar_sandbox()
    for fn in (t_orfa, t_viva, t_idade, t_pid_reusado, t_formato_antigo, t_corrompida, t_iniciar_ok, t_terceira, t_prazo,
               t_estouro, t_dependencias, t_hipoteses_insuf, t_duplicada, t_conserto, t_aposta, t_persistencia, t_fechar,
               t_guarda_alterada, t_guarda_script, t_guarda_ambiente, t_eventos):
        fn()
    for nome, ok, msg in resultados:
        print(("OK   " if ok else "FALHA") + " " + nome + (f" | {msg}" if msg else ""))
    print(f"bloco2: {sum(ok for _, ok, _ in resultados)}/{len(resultados)}")
    shutil.rmtree(TMP, ignore_errors=True)
    shutil.rmtree(SB + "-exp", ignore_errors=True)
