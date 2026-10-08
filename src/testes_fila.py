"""Testes da régua da fila de movimentos (src/unreal_macros/fila.py), sem Unreal: para cada critério, um caso que
passa e um que TEM de reprovar (os furos apontados pelo Astra em 07/10: braço parado, pé deslizando, pé abaixo do
chão, osso faltando, ordem trocada)."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from testes_v003_bloco1 import caso, rodar  # noqa: E402
from unreal_macros import fila as F  # noqa: E402


def pose(hx=0.0, hy=0.0, hz=95.0, f=90.0, mao=None, pe=(0.0, 0.0), dedo=2.0):
    """Corpo sintético olhando para f graus; mao = (lado 'L'|'R', lateral_cm, altura_acima_da_cabeca_cm)."""
    r = (math.cos(math.radians(f + 90)), math.sin(math.radians(f + 90)))  # direita do corpo

    def p(lat, z):
        return [hx + r[0] * lat, hy + r[1] * lat, z]
    o = {"Hips": [hx, hy, hz], "Spine2": [hx, hy, hz + 30], "Head": [hx, hy, hz + 60],
         "LeftArm": p(-18, hz + 45), "RightArm": p(18, hz + 45), "LeftForeArm": p(-22, hz + 25),
         "RightForeArm": p(22, hz + 25), "LeftHand": p(-25, hz), "RightHand": p(25, hz),
         "LeftUpLeg": p(-10, hz - 5), "RightUpLeg": p(10, hz - 5), "LeftLeg": p(-10, hz / 2), "RightLeg": p(10, hz / 2),
         "LeftFoot": p(-10, 8 + pe[0]), "RightFoot": p(10, 8 + pe[1]), "LeftToeBase": p(-10, dedo + pe[0]),
         "RightToeBase": p(10, dedo + pe[1])}
    if mao:
        lado, lat, alto = mao
        o[f"{'Left' if lado == 'L' else 'Right'}Hand"] = p(lat, hz + 60 + alto)
    return o


def seq_ok():
    """Sequência sintética boa: levantar (0-29), acenar (30-89), andar (90-179), parar (180-209); 30 fps."""
    faixas = [{"de": 0, "ate": 30}, {"de": 30, "ate": 90}, {"de": 90, "ate": 180}, {"de": 180, "ate": 210}]
    papeis = ["levantar", "acenar", "andar", "parar"]
    am = []
    for q in F.quadros_a_amostrar(faixas):
        if q < 30:
            o = pose(hz=50 + q * 1.5)
        elif q < 90:
            o = pose(mao=("R", 25 + 12 * math.sin((q - 30) / 4.0), 15)) if 35 <= q < 85 else pose()
        elif q < 180:
            t = q - 90
            fase = (t % 30) / 30
            o = pose(hy=t * 2.0, pe=(12 * max(0, math.sin(2 * math.pi * fase)), 12 * max(0, -math.sin(2 * math.pi * fase))))
        else:
            o = pose(hy=180.0)
        am.append((q, o))
    # as trocas acontecem entre poses quase iguais
    return am, faixas, papeis


def troca_pose(am, q, o):
    return [(x, o if x == q else p) for x, p in am]


@caso("receita: aceita levantar→acenar→andar→parar com pontes; recusa ordem trocada, campo estranho e intenção faltando")
def t_receita():
    ok = {"linhagem": "A", "tipo": "exploracao", "passos": [
        {"clipe": "Sit_To_Stand", "papel": "levantar"}, {"clipe": "Waving", "papel": "acenar"},
        {"clipe": "Idle_16", "papel": "ponte"}, {"clipe": "Start_Walking", "papel": "andar", "turn_deg": 0},
        {"clipe": "Stop_Walking_2", "papel": "parar"}]}
    assert F.validar_receita(ok) == [], F.validar_receita(ok)
    trocada = dict(ok, passos=[ok["passos"][1], ok["passos"][0]] + ok["passos"][2:])
    assert any("ordem" in m for m in F.validar_receita(trocada))
    estranho = dict(ok, passos=[dict(ok["passos"][0], play_rate=2)] + ok["passos"][1:])
    assert any("não aceitos" in m for m in F.validar_receita(estranho))
    sem_aceno = dict(ok, passos=[p for p in ok["passos"] if p["papel"] != "acenar"])
    assert any("faltam" in m for m in F.validar_receita(sem_aceno))
    assert F.assinatura(ok) == F.assinatura(dict(ok, linhagem="B")) != F.assinatura(trocada)


@caso("régua: a sequência sintética boa tira nota 0 em todos os critérios")
def t_boa():
    am, fx, pp = seq_ok()
    r = F.avaliar(am, fx, pp, 30)
    assert r["valida"] and r["nota"] == 0, (r["nota"], {k: v for k, v in r["intencoes"].items()},
                                            [(t["quadril_cm"], t["pior_osso_cm"], t["virada_deg"]) for t in r["trocas"]])


@caso("troca: mão teleportando 40 cm reprova pelo osso; quadril saltando reprova; virada de 30° reprova")
def t_trocas():
    am, fx, pp = seq_ok()
    o = dict(am[[q for q, _ in am].index(90)][1])
    o["RightHand"] = [o["RightHand"][0], o["RightHand"][1], o["RightHand"][2] + 40]
    r = F.avaliar(troca_pose(am, 90, o), fx, pp, 30)
    t = r["trocas"][1]
    assert t["pior_osso"] == "RightHand" and t["pior_osso_cm"] > 39 and r["nota"] > 1, t
    r = F.avaliar(troca_pose(am, 90, pose(hy=0.0, hz=115.0)), fx, pp, 30)
    assert r["trocas"][1]["quadril_cm"] >= 20 and r["nota"] > 0
    r = F.avaliar(troca_pose(am, 90, pose(f=120.0)), fx, pp, 30)
    assert abs(r["trocas"][1]["virada_deg"] - 30) < 0.5 and r["nota"] > 0, r["trocas"][1]["virada_deg"]


@caso("acenar: braço levantado PARADO não é aceno; mão acima por menos de 15 quadros também não")
def t_aceno():
    am, fx, pp = seq_ok()
    parado = [(q, pose(mao=("R", 25, 15)) if 35 <= q < 85 else o) for q, o in am]
    r = F.avaliar(parado, fx, pp, 30)
    assert not r["intencoes"]["acenar"]["passou"] and r["intencoes"]["acenar"]["inversoes"] == 0, r["intencoes"]["acenar"]
    curto = [(q, pose(mao=("R", 25 + 12 * math.sin(q), 15)) if 35 <= q < 45 else (pose() if 30 <= q < 90 else o))
             for q, o in am]
    assert not F.avaliar(curto, fx, pp, 30)["intencoes"]["acenar"]["passou"]


@caso("andar: deslizar 180 cm sem levantar os pés reprova; andar pouco reprova")
def t_andar():
    am, fx, pp = seq_ok()
    desliza = [(q, pose(hy=(q - 90) * 2.0) if 90 <= q < 180 else o) for q, o in am]
    r = F.avaliar(desliza, fx, pp, 30)["intencoes"]["andar"]
    assert not r["passou"] and r["deslocamento_cm"] >= 150 and r["pe_saiu_do_chao"] == {"LeftFoot": 0, "RightFoot": 0}, r
    curto = [(q, pose(hy=(q - 90) * 0.5, pe=(12 * ((q // 15) % 2), 12 * (1 - (q // 15) % 2))) if 90 <= q < 180 else o)
             for q, o in am]
    assert not F.avaliar(curto, fx, pp, 30)["intencoes"]["andar"]["passou"]


@caso("parar: quadril se mexendo no fim reprova (caminho total, não só extremos); dedo abaixo do chão reprova")
def t_parar():
    am, fx, pp = seq_ok()
    vai_volta = [(q, pose(hy=180.0 + (2.0 if q % 2 else 0.0)) if q >= 195 else o) for q, o in am]
    r = F.avaliar(vai_volta, fx, pp, 30)["intencoes"]["parar"]
    assert not r["passou"] and r["caminho_quadril_cm"] > 3, r  # extremos iguais, mas o quadril balança
    afunda = [(q, pose(hy=180.0, dedo=-6.0) if q >= 195 else o) for q, o in am]
    assert not F.avaliar(afunda, fx, pp, 30)["intencoes"]["parar"]["passou"]


@caso("levantar: começar de pé (quadril > 70) reprova")
def t_levantar():
    am, fx, pp = seq_ok()
    de_pe = [(q, pose(hz=95.0) if q < 30 else o) for q, o in am]
    assert not F.avaliar(de_pe, fx, pp, 30)["intencoes"]["levantar"]["passou"]


@caso("medição incompleta (osso faltando) não vira nota; duração > 25 s soma 1")
def t_incompleta():
    am, fx, pp = seq_ok()
    o = dict(am[5][1])
    del o["LeftToeBase"]
    r = F.avaliar(troca_pose(am, am[5][0], o), fx, pp, 30)
    assert r["valida"] is False and r["nota"] is None and "faltando" in r["motivo"], r
    assert F.avaliar(am, fx, pp, 8)["nota"] == 1.0  # 210 quadros a 8 fps = 26,25 s


@caso("regras: platô (6 sem melhorar 5%), regra de dois, exploração mínima, linhagens e limite de tentativas")
def t_regras():
    def t(n, nota, lin="A", tipo="ajuste", classe="encaixe", falhas=None):
        return {"n": n, "nota": nota, "linhagem": lin, "tipo": tipo, "classe_erro": classe, "assinatura": "x",
                "falhas": falhas or [f"troca{n}"]}
    nova = {"linhagem": "A", "tipo": "ajuste"}
    hist = [t(1, 5.0, tipo="exploracao", classe="encaixe")] + [t(i, 4.9, classe=c) for i, c in
                                                               zip(range(2, 8), ["a", "b", "a", "b", "a", "b"])]
    L = F.estado_linhagens(hist, {})["A"]
    assert L["plato"] and L["campea_nota"] == 4.9 and L["campea_n"] == 2, L  # 4,9 é a campeã, mas não é 5% melhor
    assert any("platô" in m for m in F.checar_regras(nova, hist, {}))
    dois = [t(1, 3.0, tipo="exploracao", falhas=["acenar"]), t(2, 3.0, falhas=["acenar"])]
    assert any("regra de dois" in m for m in F.checar_regras(nova, dois, {}))
    assert F.checar_regras(dict(nova, tipo="exploracao"), dois, {}) == []
    melhorou = [t(1, 3.0, tipo="exploracao", falhas=["acenar"]), t(2, 2.0, falhas=["acenar"])]
    assert F.checar_regras(nova, melhorou, {}) == []  # mesmo critério, mas a nota melhorou: não é regra de dois
    infra = [t(1, 3.0, tipo="exploracao"), t(2, None, classe="infraestrutura"), t(3, None, classe="infraestrutura")]
    assert F.estado_linhagens(infra, {})["A"]["sem_melhora"] == 0  # queda de infraestrutura não conta para platô
    nove = [t(i, 5.0 - i * 0.5, classe=c) for i, c in zip(range(1, 10), "abababab" + "a")]
    assert any("explorações" in m for m in F.checar_regras(nova, nove, {}))
    tres = [t(1, 3, "A", "exploracao"), t(2, 3, "B", "exploracao"), t(3, 3, "C", "exploracao")]
    assert any("linhagens vivas" in m for m in F.checar_regras({"linhagem": "D", "tipo": "exploracao"}, tres, {}))
    assert F.checar_regras({"linhagem": "D", "tipo": "exploracao"}, tres, {"A": "platô"}) == []
    assert any("fechada" in m for m in F.checar_regras(nova, tres, {"A": "platô"}))
    assert any("80" in m for m in F.checar_regras(nova, [t(i, 1, classe=str(i)) for i in range(80)], {}))


@caso("sucesso só com a MESMA receita nota 0 três vezes")
def t_sucesso():
    def a(n, nota, s):
        return {"n": n, "nota": nota, "assinatura": s}
    assert F.sucesso([a(1, 0, "x"), a(2, 0, "y"), a(3, 0, "x")]) is None
    assert F.sucesso([a(1, 0, "x"), a(2, 0.4, "x"), a(3, 0, "x"), a(4, 0, "x")]) == {"assinatura": "x", "vezes": 3}


if __name__ == "__main__":
    sys.exit(0 if rodar([t_receita, t_boa, t_trocas, t_aceno, t_andar, t_parar, t_levantar, t_incompleta, t_regras,
                         t_sucesso], "fila") else 1)
