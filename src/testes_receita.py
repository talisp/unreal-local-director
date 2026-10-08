"""Testes dos campos da Fase 4 (início adiantado, corte do fim, giro no fim), SEM Unreal: validação com limites, o
caso que reprova (corte maior que o clipe), assinatura compatível com a biblioteca e o formato do seq_build."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from testes_v003_bloco1 import caso, rodar  # noqa: E402
from unreal_macros import biblioteca as BIB  # noqa: E402
from unreal_macros import blocos as B  # noqa: E402
from unreal_macros import fila as F  # noqa: E402
from unreal_macros import receita as R  # noqa: E402

BOA = {"linhagem": "A", "tipo": "ajuste", "passos": [
    {"clipe": "Sit_To_Stand", "papel": "levantar"}, {"clipe": "Victory", "papel": "acenar"},
    {"clipe": "Catwalk_Walk_Forward_01", "papel": "andar"}, {"clipe": "Stop_Walking_2", "papel": "parar"}]}


def _com(i, **campos):
    r = {**BOA, "passos": [dict(p) for p in BOA["passos"]]}
    r["passos"][i].update(campos)
    return r


@caso("receita sem campo novo: validação e assinatura iguais às da régua (o bloco da noite mantém o id)")
def t_compativel():
    assert R.validar(BOA) == F.validar_receita(BOA) == []
    assert R.assinatura(BOA) == F.assinatura(BOA)
    bloco = BIB.carregar()["blocos"]["fdb93eafc4a5"]
    assert R.assinatura({"passos": bloco["receita"]}) == "fdb93eafc4a5"
    assert R.passos_para_seq_build(BOA, B.caminho) == [{"anim": B.caminho(p["clipe"]), "turn_deg": 0.0} for p in BOA["passos"]]


@caso("campos novos dentro dos limites são aceitos e vão para o seq_build; fora dos limites ou do tipo, recusados")
def t_limites():
    ok = _com(1, inicio_q=3, corte_fim_q=10, turn_fim_deg=-12.5)
    assert R.validar(ok) == [], R.validar(ok)
    p = R.passos_para_seq_build(ok, B.caminho)[1]
    assert p["inicio_q"] == 3 and p["corte_fim_q"] == 10 and p["turn_fim_deg"] == -12.5, p
    for campo, valor in (("inicio_q", -1), ("inicio_q", 121), ("inicio_q", 2.5), ("inicio_q", True),
                         ("corte_fim_q", "3"), ("turn_fim_deg", 200), ("turn_fim_deg", None)):
        m = R.validar(_com(0, **{campo: valor}))
        assert m and campo in m[0], (campo, valor, m)
    assert R.validar(_com(0, inicio_qq=1)), "campo desconhecido tem de continuar recusado pela régua"


@caso("caso que reprova: início + corte que não deixam nenhum quadro do clipe são recusados (ficha conhecida)")
def t_corte_maior_que_o_clipe():
    q = 100  # clipe curto, para início e corte caberem nos limites (0–120) e só a sobra decidir
    assert R.validar(_com(1, inicio_q=50, corte_fim_q=49), {"Victory": q}) == []  # sobra 1 quadro: vale
    m = R.validar(_com(1, inicio_q=50, corte_fim_q=50), {"Victory": q})
    assert m and "não deixa nenhum quadro" in m[0], m
    assert BIB.carregar()["fichas"]["Victory"]["quadros"] == 256  # a ficha real que o executor usa


@caso("assinatura: com campo novo ela muda; duas receitas diferentes nunca têm a mesma")
def t_assinatura():
    a, b, c = R.assinatura(_com(1, inicio_q=2)), R.assinatura(_com(1, inicio_q=3)), R.assinatura(_com(1, corte_fim_q=2))
    assert len({R.assinatura(BOA), a, b, c}) == 4, (a, b, c)
    assert R.assinatura(_com(1, inicio_q=2)) == a  # determinística


@caso("biblioteca: troca com início ou corte diferentes não é somada com a troca sem ajuste")
def t_troca_com_ajuste():
    base = {"clipe_a": "A", "clipe_b": "B", "turn_deg_b": 0,
            "medida": {"quadril_cm": 1.0, "pior_osso_cm": 1.0, "virada_deg": 0.0, "nota": 0.0}}
    ajustada = dict(base, inicio_b=3, medida={"quadril_cm": 9.0, "pior_osso_cm": 20.0, "virada_deg": 0.0, "nota": 0.3})
    c = BIB.consistencia_trocas([base, dict(base), ajustada])
    assert c["resumo"]["grupos_com_repeticao"] == 1 and c["resumo"]["nota"]["variacao_max"] == 0.0, c


if __name__ == "__main__":
    sys.exit(0 if rodar([t_compativel, t_limites, t_corte_maior_que_o_clipe, t_assinatura, t_troca_com_ajuste],
                        "receita") else 1)
