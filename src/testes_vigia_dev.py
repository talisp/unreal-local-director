"""Testes da vigia do hermes-dev (tools/vigia_dev.py), sem Hermes e sem Unreal: logs e rodadas falsos para cada
estado; o controle negativo (rodada progredindo) não pode disparar intervenção."""
import json
import os
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, "..", "tools"))
from testes_v003_bloco1 import caso, rodar  # noqa: E402
import vigia_dev as V  # noqa: E402  # pyright: ignore[reportMissingImports]

S = "20261007_205450_d29199"
T0 = V._ts("2026-10-07 21:00:00")


def L(hms, txt, sid=S):
    return f"2026-10-07 {hms},123 INFO {'[' + sid + '] ' if sid else ''}{txt}\n"


def turno(hms, msg="Leia e execute a rodada"):
    return L(hms, f"agent.turn_context: conversation turn: session={S} model=q provider=custom platform=desktop history=0 msg='{msg}'")


def api(hms, n=1, cin=40000):
    return L(hms, f"agent.conversation_loop: API call #{n}: model=q provider=custom in={cin} out=100 total=1 latency=3s")


def fim(hms, motivo="text_response(finish_reason=stop)", budget="21/200"):
    return L(hms, f"agent.conversation_loop: Turn ended: reason={motivo} model=q api_calls={budget} budget={budget}")


def rodada(n, notas=None, extra=None, fechou=False, ensaio=False):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "tentativas.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"tipo": "inicio"}) + "\n")
        for i in range(n):
            f.write(json.dumps({"n": i + 1, "tipo": "ajuste", "linhagem": "A",
                                "nota": (notas or [5.0] * n)[i], "classe_erro": "encaixe"}) + "\n")
        for e in extra or []:
            f.write(json.dumps({"tipo": e}) + "\n")
    if fechou:
        open(os.path.join(d, "FECHAMENTO.md"), "w").write("fim")
    if ensaio:
        open(os.path.join(d, "ENSAIO.md"), "w").write("fim do ensaio")
    return V.ler_rodada(d)


SAUDE = {"modelo": True, "unreal": True, "trava": "livre", "scripts_da_rodada": 0}


def obs(linhas, rd, **sd):
    return {"log": V.ler_log(linhas, {S}), "rodada": rd, "saude": dict(SAUDE, **sd), "pausa": False}


def em(minutos):
    return T0 + minutos * 60


@caso("controle negativo: rodada progredindo (turno ativo, tentativas subindo) não dispara nada")
def t_progresso():
    mem = {}
    log = [turno("20:55:00"), api("20:59:00")]
    d1 = V.decidir(obs(log, rodada(3)), mem, em(0))
    d2 = V.decidir(obs(log + [api("21:20:00")], rodada(5)), mem, em(21))
    assert d1["acoes"] == [] and d2["acoes"] == [] and d2["estado"] == "trabalhando", (d1, d2)


@caso("sem nenhuma sessão vigiada no log: espera, não relança no escuro")
def t_sem_sessao():
    d = V.decidir({"log": V.ler_log([], {S}), "rodada": rodada(0), "saude": SAUDE, "pausa": False}, {}, em(0))
    assert d == {"estado": "sem_sessao", "acoes": [], "causa": None}, d


@caso("revisão em segundo plano depois do fim do turno não conta como trabalho")
def t_revisao():
    log = [turno("20:55:00"), api("20:56:00"), fim("20:57:00", "max_iterations_reached(200/200)", "200/200"),
           turno("20:57:01", "Review the conversation above"), api("20:57:30"), fim("20:57:40", budget="3/16")]
    lg = V.ler_log(log, {S})
    assert lg["turno_ativo"] is False and lg["motivo_fim"] == "max_iterations_reached", lg


@caso("parou no limite: relança; a mesma causa de novo sem progresso: relança mudando; 3ª: crítico decide")
def t_regra_de_dois():
    mem = {}
    log = [turno("20:00:00"), api("20:30:00"), fim("20:31:00", "max_iterations_reached(200/200)", "200/200")]
    rd = rodada(4)
    d = V.decidir(obs(log, rd), mem, em(0))
    assert d["estado"] == "parou" and d["causa"] == "limite" and d["acoes"] == ["relancar"], d
    mem.setdefault("causas", []).append("limite")
    mem["relancos"], mem["relanco_pendente"] = [em(0)], em(0)
    d = V.decidir(obs(log, rd), mem, em(5))
    assert d["estado"] == "relancando" and d["acoes"] == [], d  # espera a sessão nova aparecer, não relança de novo
    mem.pop("relanco_pendente", None)
    d = V.decidir(obs(log, rd), mem, em(70))
    assert d["acoes"] == ["relancar_mudando"], d
    mem["causas"].append("limite")
    mem["relancos"].append(em(70))
    d = V.decidir(obs(log, rd), mem, em(140))
    assert d["acoes"] == ["criticar_e_decidir"], d


@caso("progresso real zera a regra de dois")
def t_progresso_zera():
    mem = {"contagem": 4, "melhor": 5.0, "causas": ["limite", "limite"], "relancos": [em(-200)]}
    log = [turno("20:00:00"), fim("20:31:00", "max_iterations_reached(200/200)", "200/200")]
    d = V.decidir(obs(log, rodada(6, [5, 5, 5, 5, 4, 3])), mem, em(0))
    assert d["acoes"] == ["relancar"] and mem["causas"] == [], (d, mem)


@caso("entre turnos há pouco tempo: espera")
def t_entre():
    log = [turno("20:50:00"), fim("20:58:00")]
    assert V.decidir(obs(log, rodada(2)), {}, em(0))["estado"] == "entre_turnos"


@caso("caiu: turno aberto e silêncio de 40 min sem script nem trava viva -> relança; com trava viva -> trabalhando")
def t_caiu():
    log = [turno("20:00:00"), api("20:20:00")]
    d = V.decidir(obs(log, rodada(2)), {}, em(40))
    assert d["causa"] == "caiu" and d["acoes"] == ["relancar"], d
    d = V.decidir(obs(log, rodada(2), trava="viva"), {}, em(40))
    assert d["estado"] == "trabalhando" and d["acoes"] == [], d
    d = V.decidir(obs(log, rodada(2), scripts_da_rodada=1), {}, em(40))
    assert d["acoes"] == [], d


@caso("infraestrutura fora: modelo ou Unreal fora -> espera, não relança; trava órfã -> libera")
def t_infra():
    log = [turno("20:00:00"), fim("20:31:00", "max_iterations_reached(200/200)", "200/200")]
    assert V.decidir(obs(log, rodada(2), modelo=False), {}, em(0)) == {"estado": "infra_fora", "acoes": [], "causa": "modelo"}
    d = V.decidir(obs(log, rodada(2), unreal=False), {}, em(0))
    assert d["estado"] == "infra_fora" and "relancar" not in d["acoes"], d
    d = V.decidir(obs([turno("20:55:00"), api("20:59:00")], rodada(2), trava="morta"), {}, em(0))
    assert d["acoes"] == ["liberar_trava"] and d["estado"] == "trabalhando", d


@caso("terminou (FECHAMENTO.md ou ENSAIO.md), pausa e estado_parcial")
def t_fim_pausa_parcial():
    log = [turno("20:00:00"), fim("20:31:00")]
    assert V.decidir(obs(log, rodada(9, fechou=True)), {}, em(0))["acoes"] == ["encerrar"]
    assert V.decidir(obs(log, rodada(3, ensaio=True)), {}, em(0))["acoes"] == ["encerrar"]  # o ensaio não é relançado
    assert not rodada(3)["terminou"]
    o = obs(log, rodada(2))
    o["pausa"] = True
    assert V.decidir(o, {}, em(0)) == {"estado": "pausado", "acoes": [], "causa": None}
    d = V.decidir(obs(log, rodada(2, extra=["estado_parcial"])), {}, em(0))
    assert d["causa"] == "estado_parcial" and d["acoes"] == ["relancar"], d


@caso("tetos: 3 relançamentos na hora -> espera; 10 na noite -> para e avisa")
def t_tetos():
    log = [turno("20:00:00"), fim("20:31:00", "max_iterations_reached(200/200)", "200/200")]
    d = V.decidir(obs(log, rodada(2)), {"relancos": [em(-50), em(-30), em(-10)]}, em(0))
    assert d["estado"] == "teto_da_hora" and d["acoes"] == [], d
    mem = {"relancos": [em(-600 + i) for i in range(10)]}
    d = V.decidir(obs(log, rodada(2)), mem, em(0))
    assert d["acoes"] == ["avisar"] and mem["desistiu"], d


@caso("relançamento que não abre sessão em 15 min -> para e avisa (não relança em loop)")
def t_relanco_falhou():
    log = [turno("20:00:00"), fim("20:31:00", "max_iterations_reached(200/200)", "200/200")]
    mem = {"relanco_pendente": em(-20), "relancos": [em(-20)]}
    d = V.decidir(obs(log, rodada(2)), mem, em(0))
    assert d["causa"] == "relanco_falhou" and d["acoes"] == ["avisar"], d


@caso("a sessão lançada pela vigia é reconhecida pelo prefixo e passa a ser vigiada")
def t_sessao_nova():
    s2 = "20261007_230000_abcdef"
    log = [turno("20:00:00"), fim("20:31:00"),
           L("23:00:00", f"agent.turn_context: conversation turn: session={s2} platform=cli msg='{V.PREFIXO} Continue a...'", s2),
           L("23:01:00", "agent.conversation_loop: API call #1: in=9000 out=1", s2)]
    lg = V.ler_log(log, {S})
    assert lg["novas"] == [s2] and lg["turno_ativo"] and lg["sessao"] == s2, lg


@caso("crítico: lê SIM/NÃO na primeira linha útil; resposta vazia é indefinida")
def t_veredito():
    assert V.veredito("**NÃO**\nmesma nota há 1 h") == "nao" and V.veredito("Sim. melhorou") == "sim"
    assert V.veredito("") == "indefinido" and V.veredito("talvez") == "indefinido"


@caso("executar: crítico diz SIM -> relança mudando; NÃO -> para e avisa (nunca relança sem limite)")
def t_executar():
    class A:
        seco, pedido, rodada = True, "p.md", tempfile.mkdtemp()
    o = obs([turno("20:00:00")], rodada(3))
    dec = {"estado": "parou", "acoes": ["criticar_e_decidir"], "causa": "limite"}
    orig = V.criticar
    try:
        V.criticar = lambda *a: "sim"
        mem = {}
        r = V.executar(dec, o, mem, A)
        assert [x["acao"] for x in r] == ["criticar_e_decidir", "relancar_mudando"] and "desistiu" not in mem, r
        V.criticar = lambda *a: "nao"
        V.PASTA = tempfile.mkdtemp()
        mem = {}
        r = V.executar(dec, o, mem, A)
        assert [x["acao"] for x in r] == ["criticar_e_decidir", "avisar"] and mem["desistiu"], r
    finally:
        V.criticar = orig


@caso("crítico tem prefixo próprio: a sessão dele NUNCA entra na lista vigiada (Astra, 07/10)")
def t_critico_separado():
    s3 = "20261007_230500_c0ffee"
    log = [turno("20:00:00"), fim("20:31:00"),
           L("23:05:00", f"agent.turn_context: conversation turn: session={s3} platform=cli msg='{V.PREFIXO_CRITICO} Você é...'", s3),
           L("23:05:30", "agent.conversation_loop: API call #1: in=900 out=1", s3)]
    lg = V.ler_log(log, {S})
    assert lg["novas"] == [] and lg["sessao"] == S and not lg["turno_ativo"], lg
    assert not V.PREFIXO_CRITICO.startswith(V.PREFIXO[:7]) or V.PREFIXO_CRITICO[:7] != V.PREFIXO[:7]


@caso("crítico: SIM zera os 'não'; resposta indefinida não conta como 'não'; dois 'não' SEGUIDOS param")
def t_contador_nao():
    class A:
        seco, pedido, rodada = True, "p.md", tempfile.mkdtemp()
    V.PASTA = tempfile.mkdtemp()
    o = obs([turno("20:00:00"), api("20:01:00")], rodada(3))
    dec = {"estado": "sem_progresso", "acoes": ["criticar"], "causa": None}
    orig, mem = V.criticar, {}
    try:
        for v, nao, parou in (("nao", 1, False), ("sim", 0, False), ("nao", 1, False), ("indefinido", 1, False),
                              ("nao", 2, True)):
            V.criticar = lambda *a, v=v: v
            V.executar(dec, o, mem, A)
            assert mem.get("nao", 0) == nao and bool(mem.get("desistiu")) == parou, (v, mem)
    finally:
        V.criticar = orig


@caso("prazo é barreira: depois do fim, nenhuma ação (nem relançar nem criticar)")
def t_prazo():
    log = [turno("20:00:00"), fim("20:31:00", "max_iterations_reached(250/250)", "250/250")]
    lim = dict(V.LIM, fim_ts=em(-1))
    d = V.decidir(obs(log, rodada(2)), {}, em(0), lim)
    assert d == {"estado": "prazo_encerrado", "acoes": [], "causa": None}, d


@caso("registro do executor: a linha 'tentativa_inicio' não conta em dobro; tentativa pendente = trabalhando")
def t_formato_executor():
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "tentativas.jsonl"), "w", encoding="utf-8") as f:
        for n in (1, 2):
            f.write(json.dumps({"tipo_linha": "tentativa_inicio", "n": n, "tipo": "ajuste", "linhagem": "A"}) + "\n")
            f.write(json.dumps({"tipo_linha": "tentativa", "n": n, "tipo": "ajuste", "linhagem": "A", "nota": 3.0 - n,
                                "classe_erro": "encaixe"}) + "\n")
        f.write(json.dumps({"tipo_linha": "tentativa_inicio", "n": 3, "tipo": "ajuste", "linhagem": "A"}) + "\n")
    json.dump({"pendente": {"n": 3, "pid": 1}}, open(os.path.join(d, "estado.json"), "w"))
    rd = V.ler_rodada(d)
    assert rd["tentativas"] == 2 and rd["melhor_nota"] == 1.0 and rd["pendente"]["n"] == 3, rd
    log = [turno("20:00:00"), api("20:20:00")]  # turno aberto e 40 min de silêncio, mas o executor está rodando
    assert V.decidir(obs(log, rd), {}, em(40))["acoes"] == []


@caso("prompt corrigido: mesmo objetivo + estado + causa + o que mudar")
def t_prompt():
    rd = rodada(4, [5, 4, 4, 4])
    p = V.prompt_corrigido("esc/RODADA.md", "work/fila", rd, "limite", True)
    assert p.startswith(V.PREFIXO) and os.path.abspath("esc/RODADA.md") in p and "nunca grave em Y:" in p and "4 tentativas" in p and "melhor nota 4" in p
    assert V.CONSELHO["limite"] in p and V.MUDAR in p and "NÃO recomece do zero" in p, p


if __name__ == "__main__":
    sys.exit(0 if rodar([t_progresso, t_sem_sessao, t_revisao, t_regra_de_dois, t_progresso_zera, t_entre, t_caiu, t_infra,
                         t_fim_pausa_parcial, t_tetos, t_relanco_falhou, t_sessao_nova, t_veredito, t_executar,
                         t_prompt, t_critico_separado, t_contador_nao, t_prazo, t_formato_executor], "vigia-dev") else 1)
