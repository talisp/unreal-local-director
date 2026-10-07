"""v0.0.2 Bloco 4 — testes do SUPERVISOR (sem Unreal). Linha do tempo simulada clonando relatórios REAIS (envelope real)
com o horário deslocado no id; eventos reais do controlador com o 'quando' deslocado."""
import copy
import datetime as dt
import json
import os
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import testes_bloco4 as T4  # noqa: E402
from testes_bloco3 import B2, X, Linha, M, caso, resultados  # noqa: E402
from unreal_macros import supervisor as S, trava as TR  # noqa: E402

T0 = time.time() - 3 * 3600  # linha do tempo começa 3 h atrás (ids no passado)


def _id(minuto: float, k: int) -> str:
    return dt.datetime.fromtimestamp(T0 + minuto * 60).strftime("%Y%m%d-%H%M%S") + f"-1-{k}"


class Tempo:
    """Escreve, numa Linha, cópias de relatórios reais em minutos simulados."""
    def __init__(self, nome):
        self.L = Linha(nome)
        self.k = 0
        self.modelos = {}

    def modelo(self, chave, *a, **kw):
        rel = self.L.macro(*a, **kw)
        os.remove(os.path.join(self.L.rel, rel["id"] + ".json"))  # o original (hora real) sai; ficam só os clones
        self.modelos[chave] = rel

    def em(self, minuto, chave, aviso=""):
        self.k += 1
        rel = copy.deepcopy(self.modelos[chave])
        rel["id"] = _id(minuto, self.k)
        rel["quando_ts"] = T0 + minuto * 60  # bloco 5: o clone do minuto X tem o horário do minuto X nos dois campos
        if aviso:
            rel["avisos"] = [aviso]
        json.dump(rel, open(os.path.join(self.L.rel, rel["id"] + ".json"), "w", encoding="utf-8"))

    def evento(self, minuto, ev):
        with open(os.path.join(self.L.exp, "eventos.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(ev, quando=dt.datetime.fromtimestamp(T0 + minuto * 60).isoformat(timespec="seconds")),
                               ensure_ascii=False) + "\n")

    def sup(self, minuto, **kw):
        return S.avaliar(T0 + minuto * 60, self.L.rel, self.L.exp, trava_path=os.path.join(self.L.raiz, "nenhuma.trava"),
                         pasta_sup=os.path.join(self.L.raiz, "supervisor"), **kw)


def _tipos(r):
    return [a["tipo"] for a in r["alarmes"]]


@caso("45 min de chamadas repetidas sem progresso útil DISPARA (atividade_sem_progresso)")
def sv_sem_progresso():
    tp = Tempo("sv1")
    tp.modelo("f", "PC_19", falhos=("deriva_xy",))
    for m in range(0, 101, 5):
        tp.em(m, "f")
    r = tp.sup(100)
    assert "atividade_sem_progresso" in _tipos(r) and r["sem_progresso_min"] >= 45, r
    assert r["alarmes"][0]["ultimo_progresso"]["tipo"] == "degrau:abortar", r["alarmes"][0]
    assert r["alarmes"][0]["acao_recomendada"]


@caso("progresso real (melhora medida) reinicia o relógio")
def sv_progresso():
    tp = Tempo("sv2")
    tp.modelo("f2", "PC_19", falhos=("deriva_xy", "pes_no_chao"))
    tp.modelo("f1", "PC_19", falhos=("deriva_xy",))
    for m in range(0, 81, 5):
        tp.em(m, "f2")
    tp.em(90, "f1")
    r = tp.sup(100)
    assert not r["alarmes"] and r["sem_progresso_min"] == 10.0, r


@caso("texto livre ('progredi') em avisos e diário NÃO reinicia o relógio")
def sv_texto():
    tp = Tempo("sv3")
    tp.modelo("f", "PC_19", falhos=("deriva_xy",))
    for m in range(0, 101, 5):
        tp.em(m, "f", aviso="progredi! estou quase lá")
    open(os.path.join(tp.L.raiz, "diario.jsonl"), "w", encoding="utf-8").write('{"nota": "progredi muito"}\n')
    assert "atividade_sem_progresso" in _tipos(tp.sup(100))


@caso("espera legítima longa (corrida em andamento; escalada para humano) NÃO dispara")
def sv_espera():
    tp = Tempo("sv4")
    tp.modelo("f", "PC_19", falhos=("deriva_xy",))
    tp.em(0, "f")
    tp.evento(5, {"evento": "corrida_iniciada", "experimento": "e1", "n": 1, "script": "src/x.py", "prazo_s": 3600})  # dentro do prazo (bloco 5: além dele vira corrida_perdida)
    r = tp.sup(60)
    assert not r["alarmes"] and r["esperas_ativas"][0]["tipo"] == "corrida", r
    tp2 = Tempo("sv4b")
    tp2.modelo("f", "PC_19", falhos=("deriva_xy",))
    tp2.em(0, "f")
    tp2.evento(5, {"evento": "escalada", "experimento": "L", "motivo": "diagnóstico entregue ao operador"})
    r2 = tp2.sup(90)
    assert not r2["alarmes"] and r2["esperas_ativas"][0]["tipo"] == "humano", r2


@caso("violação dispara mesmo com atividade, escreve PAUSA e as macros/experimentos passam a recusar")
def sv_violacao():
    tp = Tempo("sv5")
    tp.modelo("ok", "PC_19")
    tp.em(0, "ok")
    tp.evento(1, {"evento": "recusa", "experimento": "x", "acao": "rodar",
                  "motivo": "guarda.py da cópia do experimento foi ALTERADA: recuso rodar"})
    r = tp.sup(2)
    assert "tentativa_proibida" in _tipos(r) and r["pausa"], r
    assert os.path.exists(os.path.join(tp.L.raiz, "supervisor", "PAUSA"))
    orig = M.RAIZ_WORK
    M.RAIZ_WORK = tp.L.raiz
    try:
        rel = M.medir_personagem("PC_19")
        assert rel["ok"] is False and "PAUSADO" in rel["bloqueio"], rel["bloqueio"]
        try:
            X.iniciar("pausado", "experimento", "não deve abrir durante a pausa", hipoteses=[B2.H_A, B2.H_B],
                      sandbox=B2.SB, pasta=tp.L.exp)
            raise AssertionError("abriu experimento pausado")
        except X.Recusa as e:
            assert "PAUSADO" in str(e)
    finally:
        M.RAIZ_WORK = orig


@caso("violação: guarda.py do sandbox alterada no master é detectada (sha diferente da base)")
def sv_guarda():
    import hashlib
    sb = os.path.join(T4.TMP, "sb-guarda")
    os.makedirs(os.path.join(sb, "src", "unreal_macros"), exist_ok=True)
    g = os.path.join(sb, "src", "unreal_macros", "guarda.py")
    open(g, "w", encoding="utf-8").write("# GUARDA\n")
    for cmd in (["init", "-q", "-b", "master"], ["add", "-A"], ["commit", "-qm", "base"]):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *cmd], cwd=sb, check=True, capture_output=True)
    base = hashlib.sha256("# GUARDA\n".encode()).hexdigest()
    tp = Tempo("sv5b")
    tp.modelo("ok", "PC_19")
    tp.em(0, "ok")
    assert "guarda_alterada" not in _tipos(tp.sup(1, sandbox=sb, guarda_sha_base=base))
    open(g, "a", encoding="utf-8").write("def checar(*a, **k): return None\n")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "mexe"], cwd=sb, check=True, capture_output=True)
    assert "guarda_alterada" in _tipos(tp.sup(2, sandbox=sb, guarda_sha_base=base))


@caso("mesma estratégia com NOMES DIFERENTES de experimento é vista pela visão de sessão")
def sv_sessao():
    L = Linha("sv6")
    for nome in ("tentativa-a", "tentativa-b"):
        X.iniciar(nome, "experimento", "mesma estratégia, outro nome", hipoteses=[B2.H_A, B2.H_B], sandbox=B2.SB, pasta=L.exp)
        X.rodar(nome, "src/falha.py", pasta=L.exp)
    import unreal_macros.emperramento as E
    itens = E.carregar_historico(L.rel, L.exp)
    assert not E.avaliar(itens, "tentativa-a")["emperrado"] and not E.avaliar(itens, "tentativa-b")["emperrado"]
    r = S.avaliar(time.time(), L.rel, L.exp, trava_path=os.path.join(L.raiz, "x.trava"), pasta_sup=os.path.join(L.raiz, "sup"))
    a = [x for x in r["alarmes"] if x["tipo"] == "emperramento_de_sessao"]
    assert a and a[0]["linhas"] == ["tentativa-a", "tentativa-b"], r


@caso("atividade normal (resultados novos a cada 10 min) NÃO gera falso positivo")
def sv_normal():
    tp = Tempo("sv7")
    combos = [("deriva_xy",), ("pes_no_chao",), ("deriva_xy", "pes_no_chao"), ("silhueta_de_pe",), ("pes_plantados",), ()]
    for i, f in enumerate(combos):
        tp.modelo(f"c{i}", f"A{i}", falhos=f)
        tp.em(i * 10, f"c{i}")
    r = tp.sup(55)
    assert not r["alarmes"], r


@caso("vida: trava com dono morto -> trava_orfa; dono vivo segurando 30+ min sem relatório -> macro_presa")
def sv_vida():
    tp = Tempo("sv8")
    tp.modelo("ok", "PC_19")
    tp.em(0, "ok")
    tv = os.path.join(tp.L.raiz, "t.trava")
    subprocess.run([sys.executable, "-c", B2.TOMA_E_SAI.format(aqui=AQUI, p=tv)], check=True)
    r = S.avaliar(time.time(), tp.L.rel, tp.L.exp, trava_path=tv, pasta_sup=os.path.join(tp.L.raiz, "s"))
    assert "trava_orfa" in _tipos(r), r
    os.remove(tv)
    proc = subprocess.Popen([sys.executable, "-c", B2.TOMA_E_DORME.format(aqui=AQUI, p=tv)])
    try:
        for _ in range(100):
            if os.path.exists(tv):
                break
            time.sleep(0.1)
        info = json.load(open(tv, encoding="utf-8"))
        info["desde"] = time.time() - 31 * 60
        json.dump(info, open(tv, "w", encoding="utf-8"))
        r2 = S.avaliar(time.time(), tp.L.rel, tp.L.exp, trava_path=tv, pasta_sup=os.path.join(tp.L.raiz, "s2"))
        assert "macro_presa" in _tipos(r2), r2
    finally:
        proc.kill()


@caso("alarmes registrados de forma determinística e idempotente (reavaliar não duplica)")
def sv_registro():
    tp = Tempo("sv9")
    tp.modelo("f", "PC_19", falhos=("deriva_xy",))
    for m in range(0, 101, 5):
        tp.em(m, "f")
    for _ in range(3):
        tp.sup(100)
    linhas = open(os.path.join(tp.L.raiz, "supervisor", "alarmes.jsonl"), encoding="utf-8").read().strip().splitlines()
    assert len(linhas) == len({json.loads(l)["chave"] for l in linhas}) >= 1
    a = json.loads(linhas[0])
    assert {"motivo", "ultimo_progresso", "evidencia", "acao_recomendada"} <= set(a)


SECAO_SUPERVISOR = [sv_sem_progresso, sv_progresso, sv_texto, sv_espera, sv_violacao, sv_guarda, sv_sessao, sv_normal,
                    sv_vida, sv_registro]

if __name__ == "__main__":
    B2._montar_sandbox()
    T4.rodar(SECAO_SUPERVISOR, "bloco4-supervisor")
