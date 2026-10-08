"""Testes do executor da fila (tools/fila_executor.py) nas partes SEM Unreal: recusa antes de tocar na cena, registro
que resiste a queda (linha JSON cortada, tentativa pendente de dono morto), estado gravado em disco."""
import json
import os
import sys
import tempfile

PASTA = tempfile.mkdtemp()
os.environ["FILA_PASTA"] = PASTA
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(AQUI, "..", "tools"))
from testes_v003_bloco1 import caso, rodar  # noqa: E402
import fila_executor as X  # noqa: E402  # pyright: ignore[reportMissingImports]

BOA = {"linhagem": "A", "tipo": "exploracao", "hipotese": "teste", "passos": [
    {"clipe": "Sit_To_Stand", "papel": "levantar"}, {"clipe": "Waving", "papel": "acenar"},
    {"clipe": "Start_Walking", "papel": "andar"}, {"clipe": "Stop_Walking_2", "papel": "parar"}]}


def limpar():
    for f in os.listdir(PASTA):
        if os.path.isfile(os.path.join(PASTA, f)):
            os.remove(os.path.join(PASTA, f))


@caso("receita inválida é recusada com o motivo, sem reservar número nem tocar no Unreal")
def t_recusa():
    limpar()
    # Relógio fixo "antes das 07:30": sem isto, rodado de manhã o caso recebe a recusa da HORA (08/10, 4/5 às 09:55),
    # que não é o que ele testa.
    depois_da_hora, X.depois_da_hora = X.depois_da_hora, lambda: False
    try:
        n, m = X.preparar(dict(BOA, passos=BOA["passos"][::-1]))
        assert n == 1 and any("ordem" in x for x in m), m
        assert not os.path.exists(os.path.join(PASTA, "estado.json"))
        n, m = X.preparar(BOA)
        assert m == [], m
    finally:
        X.depois_da_hora = depois_da_hora


@caso("linha JSON cortada por queda é ignorada; as outras continuam valendo")
def t_cortada():
    limpar()
    with open(os.path.join(PASTA, "tentativas.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"tipo_linha": "tentativa", "n": 1, "linhagem": "A", "tipo": "exploracao", "nota": 2.0,
                            "assinatura": "x", "receita": BOA["passos"]}) + "\n")
        f.write('{"tipo_linha": "tentativa", "n": 2, "nota": 1.')  # queda no meio da escrita
    assert [t["n"] for t in X.tentativas_validas()] == [1]
    r = X.estado_resumo()
    assert r["tentativas"] == 1 and r["linhagens"]["A"]["campea_nota"] == 2.0, r


@caso("tentativa pendente de dono MORTO vira 'interrompida'; de dono VIVO bloqueia a próxima")
def t_pendente():
    limpar()
    X._gravar_estado({"proximo_n": 4, "pendente": {"n": 3, "pid": 999999, "desde": "x", "seq": "/Game/S.S"}, "fechadas": {}})
    p = X.recuperar_pendente()
    assert p["n"] == 3 and X._estado()["pendente"] is None and X._estado()["runs_para_limpar"] == ["999999"]
    assert X._estado()["seqs_para_apagar"] == ["/Game/S.S"]
    assert X._ler_jsonl("tentativas.jsonl")[-1]["tipo_linha"] == "tentativa_interrompida"
    X._gravar_estado({"proximo_n": 5, "pendente": {"n": 4, "pid": os.getpid(), "desde": "x"}, "fechadas": {}})
    assert X.recuperar_pendente() is None
    n, m = X.preparar(BOA)
    assert any("ainda está rodando" in x for x in m), m


@caso("fechar-linhagem grava no estado e no registro; a linhagem fechada é recusada")
def t_fechar():
    limpar()
    assert X.main(["fechar-linhagem", "A", "platô", "de", "6"]) == 0
    assert X._estado()["fechadas"] == {"A": "platô de 6"}
    _, m = X.preparar(BOA)
    assert any("fechada" in x for x in m), m


@caso("resultado de tentativa desconhecida e receita ilegível respondem curto, sem quebrar")
def t_resultado():
    limpar()
    assert X.main(["resultado", "42"]) == 0
    arq = os.path.join(PASTA, "ruim.json")
    open(arq, "w").write("{nao é json")
    assert X.main(["tentar", arq]) == 1


def _tentativa_zero(n: int, escala: float = 1.0):
    """Linhas que o executor grava numa tentativa com nota 0 (formato real), mais as amostras."""
    from unreal_macros import fila as F
    receita = dict(BOA, passos=[dict(p) for p in BOA["passos"]])
    faixas = [{"clipe": f"{p['clipe']}_Anim", "de": i * 30, "ate": (i + 1) * 30, "avanco_cm": 0.0}
              for i, p in enumerate(receita["passos"])]
    ossos = {o: [0.0, float(i), 100.0] for i, o in enumerate(F.OSSOS)}
    amostras = [(q, ossos) for q in F.quadros_a_amostrar(faixas)]
    cond = dict(X.CONDICOES, escala=escala)
    base = {"n": n, "linhagem": "A", "tipo": "ajuste", "receita": receita["passos"], "assinatura": F.assinatura(receita),
            "versoes": X.versoes(), "fps": X.FPS, "condicoes": cond}
    X._acrescentar("tentativas.jsonl", dict(base, tipo_linha="tentativa", nota=0.0, passou=True, quando="agora",
                                            montagem={"faixas": faixas},
                                            avaliacao={"valida": True, "nota": 0.0, "duracao_s": 4.0,
                                                       "intencoes": {p: {"passou": True} for p in F.PAPEIS}}))
    for i in range(len(faixas) - 1):
        a, b = receita["passos"][i], receita["passos"][i + 1]
        X._acrescentar("encaixes.jsonl", {"n": n, "troca": i, "valida": True, "clipe_a": a["clipe"], "clipe_b": b["clipe"],
                                          "ossos_antes": ossos, "ossos_depois": ossos, "quadril_cm": 0.0,
                                          "pior_osso": "Hips", "pior_osso_cm": 0.0, "virada_deg": 0.0, "nota": 0.0,
                                          "fps": X.FPS, "versoes": base["versoes"], "condicoes": cond})
    X._gravar_amostras(n, amostras)
    return amostras, faixas


@caso("B5: o bloco nasce na 3ª nota 0 (nenhum antes), com amostras e condições gravadas; escala diferente não soma")
def t_grava_bloco():
    import tempfile
    from unreal_macros import biblioteca as BIB
    from unreal_macros import fila as F
    limpar()
    with tempfile.TemporaryDirectory() as bib:
        for n in (1, 2):
            _tentativa_zero(n)
            assert X.registrar_na_biblioteca(bib)["blocos"] == [], n  # caso que reprova: 1 ou 2 notas 0 não são bloco
        _tentativa_zero(3, escala=1.2)  # 3ª nota 0, mas em outra escala: não soma com as duas primeiras
        assert X.registrar_na_biblioteca(bib)["blocos"] == []
        amostras, faixas = _tentativa_zero(4)
        r = X.registrar_na_biblioteca(bib)
        assert r["ok"] and len(r["blocos"]) == 1, r
        b = BIB.carregar(bib)["blocos"][r["blocos"][0]]
        assert b["tentativas"] == [1, 2, 4] and b["condicoes"]["origem"]["escala"] == "gravado pelo executor", b["tentativas"]
        assert len(b["amostras"]) == 3 and all(os.path.exists(os.path.join(bib, a)) for a in b["amostras"]), b["amostras"]
        completo = BIB.recalcular_bloco_completo(b, bib)
        # por construção: prova que as amostras chegam inteiras e na ordem (a nota sai igual à de fila.avaliar)
        esperado = F.avaliar(amostras, faixas, [p["papel"] for p in BOA["passos"]], X.FPS)["nota"]
        assert completo["status"] == "ok" and completo["notas"] == {1: esperado, 2: esperado, 4: esperado}, completo
        assert BIB.consultar_bloco(BIB.carregar(bib), b["id"], dict(BIB.condicoes_atuais(), escala=1.2))["status"] \
            == "medir_de_novo"
        assert len(X._ler_jsonl("biblioteca.jsonl")) == 4  # cada nota 0 deixa uma linha do que foi gravado


if __name__ == "__main__":
    sys.exit(0 if rodar([t_recusa, t_cortada, t_pendente, t_fechar, t_resultado, t_grava_bloco], "fila-executor") else 1)
