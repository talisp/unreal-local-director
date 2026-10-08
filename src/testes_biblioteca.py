"""Testes da biblioteca de blocos (Fase 3), SEM Unreal: a importação com dados sintéticos (casos que reprovam) e a
biblioteca commitada (importada da noite de 07/10)."""
import copy
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from testes_v003_bloco1 import caso, rodar  # noqa: E402
from unreal_macros import biblioteca as BIB  # noqa: E402
from unreal_macros import fila as F  # noqa: E402

V = {"regua": "r1", "executor": "e1", "toolset": "s1"}
OSSO = {n: [0.0, 0.0, 100.0] for n in F.OSSOS}
RECEITA = [{"clipe": "A", "papel": "levantar"}, {"clipe": "B", "papel": "acenar"}]
INTENCOES = {p: {"passou": True} for p in F.PAPEIS}


def _tentativa(n, nota, assin="x1", regua="r1"):
    return {"tipo_linha": "tentativa", "n": n, "receita": RECEITA, "assinatura": assin, "nota": nota, "fps": 30,
            "versoes": dict(V, regua=regua), "quando": f"2026-10-07T2{n}:00:00",
            "avaliacao": {"valida": True, "nota": nota, "intencoes": INTENCOES, "duracao_s": 10.0},
            "montagem": {"faixas": [{"clipe": "A_Anim", "de": 0, "ate": 30, "avanco_cm": 10.0},
                                    {"clipe": "B_Anim", "de": 30, "ate": 90, "avanco_cm": 0.0}]}}


def _encaixe(n):
    return {"n": n, "troca": 0, "valida": True, "clipe_a": "A", "clipe_b": "B", "quadros": [29, 30], "turn_deg_b": 0,
            "ossos_antes": OSSO, "ossos_depois": OSSO, "quadril_cm": 0.0, "pior_osso": "Hips", "pior_osso_cm": 0.0,
            "virada_deg": 0.0, "nota": 0.0, "fps": 30, "versoes": V}


def _rodada(tmp, tentativas, encaixes, cortar=False):
    pasta = os.path.join(tmp, "rodada")
    os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, "tentativas.jsonl"), "w", encoding="utf-8") as f:
        for t in tentativas:
            f.write(json.dumps(t) + "\n")
        if cortar:
            f.write(json.dumps(_tentativa(99, 0))[:57])  # queda no meio da gravação
    with open(os.path.join(pasta, "encaixes.jsonl"), "w", encoding="utf-8") as f:
        for e in encaixes:
            f.write(json.dumps(e) + "\n")
    return pasta


@caso("3 notas 0 com a mesma assinatura e a mesma régua viram 1 bloco; 2 notas 0 não viram")
def t_bloco_so_com_tres():
    with tempfile.TemporaryDirectory() as tmp:
        r = BIB.importar_rodada(_rodada(tmp, [_tentativa(1, 0), _tentativa(2, 0), _tentativa(3, 0.5)],
                                        [_encaixe(n) for n in (1, 2, 3)]), "teste")
        assert r["blocos"] == [], r["blocos"]  # caso que reprova: só 2 notas 0
        r = BIB.importar_rodada(_rodada(tmp, [_tentativa(1, 0), _tentativa(2, 0), _tentativa(3, 0)],
                                        [_encaixe(n) for n in (1, 2, 3)]), "teste")
        assert [b["id"] for b in r["blocos"]] == ["x1"] and r["blocos"][0]["tentativas"] == [1, 2, 3], r["blocos"]
        assert len(r["blocos"][0]["trocas"]) == 3 and len(r["trocas"]) == 3


@caso("3 notas 0 com réguas diferentes NÃO viram bloco (não se somam medidas de réguas diferentes)")
def t_regua_diferente_nao_soma():
    with tempfile.TemporaryDirectory() as tmp:
        ts = [_tentativa(1, 0), _tentativa(2, 0), _tentativa(3, 0, regua="r2")]
        r = BIB.importar_rodada(_rodada(tmp, ts, []), "teste")
        assert r["blocos"] == [], r["blocos"]


@caso("linha cortada é ignorada e contada; o resto entra")
def t_linha_cortada():
    with tempfile.TemporaryDirectory() as tmp:
        ts = [_tentativa(n, 0) for n in (1, 2, 3)]
        r = BIB.importar_rodada(_rodada(tmp, ts, [_encaixe(1)], cortar=True), "teste")
        assert r["cortadas"] == 1 and len(r["blocos"]) == 1 and len(r["trocas"]) == 1, r["cortadas"]


@caso("importar duas vezes dá os mesmos bytes (o id substitui, não duplica)")
def t_idempotente():
    with tempfile.TemporaryDirectory() as tmp:
        pasta, bib = _rodada(tmp, [_tentativa(n, 0) for n in (1, 2, 3)], [_encaixe(n) for n in (1, 2, 3)]), \
            os.path.join(tmp, "bib")
        BIB.mesclar(bib, BIB.importar_rodada(pasta, "teste"))
        antes = {t: open(os.path.join(bib, f"{t}.jsonl"), "rb").read() for t in BIB.TIPOS}
        c = BIB.mesclar(bib, BIB.importar_rodada(pasta, "teste"))
        assert {t: open(os.path.join(bib, f"{t}.jsonl"), "rb").read() for t in BIB.TIPOS} == antes
        assert c == {"blocos": 1, "trocas": 3, "fichas": 2, "escolhas": 0}, c


@caso("troca cujo clipe não bate com a receita fica sem papel (não inventa)")
def t_papel_nao_inventado():
    with tempfile.TemporaryDirectory() as tmp:
        e = copy.deepcopy(_encaixe(1))
        e["clipe_b"] = "Outro"
        r = BIB.importar_rodada(_rodada(tmp, [_tentativa(1, 0)], [e]), "teste")
        assert r["trocas"][0]["papel_a"] == "levantar" and r["trocas"][0]["papel_b"] is None, r["trocas"][0]


@caso("biblioteca commitada (noite de 07/10): 1 bloco (fdb93eafc4a5, t18-t20), 138 trocas, ficha de todo clipe")
def t_biblioteca_da_noite():
    b = BIB.carregar()
    assert b["cortadas"] == {t: 0 for t in BIB.TIPOS}, b["cortadas"]
    assert list(b["blocos"]) == ["fdb93eafc4a5"], list(b["blocos"])
    bloco = b["blocos"]["fdb93eafc4a5"]
    assert bloco["tentativas"] == [18, 19, 20] and bloco["notas"] == [0.0, 0.0, 0.0], bloco["tentativas"]
    assert len(b["trocas"]) == 138 and all(t["condicoes"]["regua"] for t in b["trocas"].values())
    assert {p["clipe"] for p in bloco["receita"]} <= set(b["fichas"]), "clipe do bloco sem ficha"
    assert all(t["papel_a"] and t["papel_b"] for t in b["trocas"].values()), "troca sem papel"


@caso("B2: as 138 trocas recalculadas dos ossos gravados dão EXATAMENTE as medidas gravadas na noite")
def t_recalculo_fiel():
    tr = BIB.carregar()["trocas"]
    dif = [t["id"] for t in tr.values() if BIB.medir_troca(t["ossos_antes"], t["ossos_depois"]) != t["medida"]]
    assert len(tr) == 138 and dif == [], dif[:5]


@caso("B2: t18-t20 recalculadas dão nota 0; régua mais dura (osso 10 cm) sobe a nota; régua diferente fica marcada")
def t_recalculo_bloco():
    b = BIB.carregar()
    bloco = b["blocos"]["fdb93eafc4a5"]
    r = BIB.recalcular_bloco(bloco, b["trocas"])
    assert r["notas"] == {18: 0.0, 19: 0.0, 20: 0.0} and not r["regua_diferente"], r["notas"]
    duro = BIB.recalcular_bloco(bloco, b["trocas"], lim=dict(F.LIM, osso_cm=10.0))
    assert all(n > 0 for n in duro["notas"].values()), duro["notas"]  # caso que reprova: a régua mudou o resultado
    outra = BIB.recalcular_bloco(bloco, b["trocas"], regua="outra-regua")
    assert outra["regua_diferente"] and "medir de novo" in outra["intencoes"], outra


@caso("B2: a mesma troca em receitas diferentes dá o mesmo custo (variação de nota 0 nos grupos repetidos)")
def t_consistencia_trocas():
    c = BIB.consistencia_trocas(BIB.carregar()["trocas"].values())["resumo"]
    assert c["grupos_com_repeticao"] >= 10 and c["nota"]["variacao_max"] == 0.0, c
    assert c["quadril_cm"]["variacao_max"] <= 0.05 and c["pior_osso_cm"]["variacao_max"] <= 0.05, c


@caso("B3: nas condições de agora o bloco da fila sai 'validado', com receita que o executor aceita sem mudar nada")
def t_consulta_valida():
    b, c = BIB.carregar(), BIB.condicoes_atuais()
    r = BIB.consultar_bloco(b, "fdb93eafc4a5", c)
    assert r["status"] == "validado" and r["frase"] == BIB.FRASE_VALIDO, r
    assert F.validar_receita(r["receita"]) == [], F.validar_receita(r["receita"])
    assert F.assinatura(r["receita"]) == "fdb93eafc4a5", "a receita devolvida não é a do bloco"


@caso("B3: outro esqueleto, outra escala, outro FPS, outra régua ou condição faltando -> 'medir de novo', sem a receita")
def t_consulta_recusa():
    b, c = BIB.carregar(), BIB.condicoes_atuais()
    for mudanca, chave in (({"personagem": "/Game/Outro/SK_Outro.SK_Outro"}, "personagem"), ({"escala": 1.1}, "escala"),
                           ({"fps": 24}, "fps"), ({"regua": "outra"}, "regua"),
                           ({"root_motion": "forcado"}, "root_motion")):
        r = BIB.consultar_bloco(b, "fdb93eafc4a5", dict(c, **mudanca))
        assert r["status"] == "medir_de_novo" and "receita" not in r, r
        assert any(m.startswith(chave) for m in r["motivos"]), r["motivos"]
    sem = {k: v for k, v in c.items() if k != "escala"}
    r = BIB.consultar_bloco(b, "fdb93eafc4a5", sem)
    assert r["status"] == "medir_de_novo" and "não informado" in r["motivos"][0], r


@caso("B3: executor ou toolset diferentes só geram aviso; bloco inexistente é recusado com motivo")
def t_consulta_avisos():
    b, c = BIB.carregar(), BIB.condicoes_atuais()
    r = BIB.consultar_bloco(b, "fdb93eafc4a5", dict(c, executor="outro", toolset="outro"))
    assert r["status"] == "validado" and len(r["avisos"]) == 2, r
    r = BIB.consultar_bloco(b, "nao-existe", c)
    assert r["status"] == "nao_existe" and r["blocos"] == ["fdb93eafc4a5"], r


@caso("B4: as consultas respondem com os dados da noite e recusam nome ou papel inexistente com motivo")
def t_consultas():
    b, c = BIB.carregar(), BIB.condicoes_atuais()
    lb = BIB.listar_blocos(b, c)
    assert lb["total"] == 1 and lb["blocos"][0]["status"] == "validado", lb
    assert BIB.listar_blocos(b, dict(c, escala=2.0))["blocos"][0]["status"] == "medir_de_novo"
    h = BIB.historico_bloco(b, "fdb93eafc4a5")
    assert h["status"] == "ok" and len(h["trocas"]) == 21 and h["notas"] == [0.0, 0.0, 0.0], (h["status"], len(h["trocas"]))
    assert BIB.historico_bloco(b, "zzz")["status"] == "nao_existe"
    t = BIB.consultar_trocas(b, "Sit_To_Stand", "acenar", c)
    assert t["status"] == "ok" and t["trocas"][0]["para"] == "Victory" and t["trocas"][0]["passa_na_regua"], t["trocas"][:1]
    notas = [x["medida"]["nota"] for x in t["trocas"]]
    assert notas == sorted(notas), notas  # da melhor para a pior
    errado = BIB.consultar_trocas(b, "Sit_To_Stnd", "acenar")
    assert errado["status"] == "sem_medida" and "Sit_To_Stand" in errado["parecidos"], errado
    assert BIB.consultar_trocas(b, "Sit_To_Stand", "voar")["status"] == "recusado"
    f = BIB.ficha_clipe(b, "Victory")
    assert f["status"] == "ok" and f["papeis"]["acenar"]["passou"] >= 3, f
    assert BIB.ficha_clipe(b, "Vitory")["status"] == "nao_existe"


PY_RUNTIME = r"<repo>\venv\Scripts\python.exe"  # o único com mcp/numpy (servidor)


@caso("B4: o servidor florentia-macros registra as 5 consultas e elas devolvem JSON (Python do venv, offline)")
def t_servidor_registra():
    import subprocess
    codigo = ("import asyncio, json, server as S\n"
              "n = {t.name for t in asyncio.run(S.mcp.list_tools())}\n"
              "q = ('listar_blocos', 'consultar_bloco', 'historico_bloco', 'consultar_trocas', 'ficha_clipe')\n"
              "r = json.loads(S.consultar_bloco('fdb93eafc4a5'))\n"
              "print(json.dumps({'faltam': [x for x in q if x not in n], 'status': r['status']}))\n")
    assert os.path.exists(PY_RUNTIME), f"Python do venv não encontrado em {PY_RUNTIME}"
    r = subprocess.run([PY_RUNTIME, "-B", "-c", codigo], cwd=os.path.dirname(os.path.abspath(__file__)),
                       capture_output=True, timeout=120, env=dict(os.environ, UNREAL_MACROS_OFFLINE="1"))
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")[-400:]
    out = json.loads(r.stdout.decode("utf-8").strip().splitlines()[-1])
    assert out == {"faltam": [], "status": "validado"}, out


if __name__ == "__main__":
    sys.exit(0 if rodar([t_bloco_so_com_tres, t_regua_diferente_nao_soma, t_linha_cortada, t_idempotente,
                         t_papel_nao_inventado, t_biblioteca_da_noite, t_recalculo_fiel, t_recalculo_bloco,
                         t_consistencia_trocas, t_consulta_valida, t_consulta_recusa, t_consulta_avisos, t_consultas,
                         t_servidor_registra], "biblioteca") else 1)
