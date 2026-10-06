"""v0.0.2 Bloco 4 — passagem de sessão, rotação e INTEGRAÇÃO FINAL offline (sem Unreal).
Formatos reais: relatórios clonados do envelope real, controlador real, detector/resolver/supervisor reais."""
import json
import os
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import testes_bloco4 as T4  # noqa: E402
from testes_bloco3 import B2, E, X, Linha, M, caso, resultados  # noqa: E402
from testes_bloco4_sup import T0, Tempo  # noqa: E402
from unreal_macros import diario, direcao as D, resolver as RS, rotacao as R, sessao as SS, supervisor as S  # noqa: E402

PASSAGEM = """
import sys, json
sys.path.insert(0, {aqui!r})
from unreal_macros import sessao
p = sessao.passagem(agora={agora!r}, pasta_rel={rel!r}, pasta_exp={exp!r}, pasta_sessao={ses!r},
                    trava_path={trava!r}, pasta_sup={sup!r}, pasta_licoes={lic!r})
print("PASSAGEM " + json.dumps(p, ensure_ascii=False, default=str))
"""


def _passagem_outro_processo(L, agora):
    cod = PASSAGEM.format(aqui=AQUI, agora=agora, rel=L.rel, exp=L.exp, ses=os.path.join(L.raiz, "sessao"),
                          trava=os.path.join(L.raiz, "nenhuma.trava"), sup=os.path.join(L.raiz, "supervisor"),
                          lic=os.path.join(L.raiz, "licoes"))
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", cod], capture_output=True, text=True, encoding="utf-8")
    linha = [l for l in r.stdout.splitlines() if l.startswith("PASSAGEM ")]
    assert linha, r.stderr[-1000:]
    return linha[0][9:], json.loads(linha[0][9:])


# ---------- sessão ----------
@caso("processo novo recupera o estado mínimo correto (objetivo, experimento aberto, último progresso, pendências)")
def se_recupera():
    L = Linha("se1")
    SS.definir_objetivo("fazer a plateia conversar sem falso reprovado", "P06", os.path.join(L.raiz, "sessao"))
    X.iniciar("se-exp", "experimento", "linha atual da sessão", hipoteses=[B2.H_A, B2.H_B], sandbox=B2.SB, pasta=L.exp, pedido="P06")
    X.rodar("se-exp", "src/falha.py", pasta=L.exp)
    RS.registrar_uso_licao("L-ver-01", "se-exp", os.path.join(L.raiz, "licoes"))
    _, p = _passagem_outro_processo(L, time.time())
    assert p["objetivo"]["pedido"] == "P06" and p["experimentos_abertos"][0]["nome"] == "se-exp"
    assert p["experimentos_abertos"][0]["corridas"] == 1 and p["ultimo_progresso"]["tipo"] == "resultado_novo"
    assert p["pendencias"]["experimentos_abertos"] == ["se-exp"] and len(p["pendencias"]["licoes_sem_voto"]) == 1


@caso("passagem não despeja histórico: 200 relatórios e ela continua pequena (<= 4 KB) e sem lista de relatórios")
def se_pequena():
    tp = Tempo("se2")
    tp.modelo("f", "PC_19", falhos=("deriva_xy",))
    for i in range(200):
        tp.em(i * 0.5, "f")
    texto, p = _passagem_outro_processo(tp.L, T0 + 101 * 60)
    assert len(texto) <= SS.TAMANHO_MAX, len(texto)
    assert "relatorios" not in p and texto.count("-1-") < 10


@caso("lições relevantes continuam disponíveis para a sessão nova (linha emperrada)")
def se_licoes():
    L = Linha("se3")
    X.iniciar("se-emp", "experimento", "linha emperrada", hipoteses=[B2.H_A, B2.H_B], sandbox=B2.SB, pasta=L.exp)
    X.rodar("se-emp", "src/falha.py", pasta=L.exp)
    X.rodar("se-emp", "src/falha.py", pasta=L.exp)
    _, p = _passagem_outro_processo(L, time.time())
    assert p["experimentos_abertos"][0]["emperrado"] and p["experimentos_abertos"][0]["degrau"] == "cutucar"
    assert [l["id"] for l in p["licoes_relevantes"]] == ["L-est-01"], p["licoes_relevantes"]


@caso("espera e bloqueio ativos sobrevivem à troca de sessão (corrida em andamento + PAUSA)")
def se_bloqueio():
    tp = Tempo("se4")
    tp.modelo("ok", "PC_19")
    tp.em(0, "ok")
    tp.evento(5, {"evento": "corrida_iniciada", "experimento": "e1", "n": 1, "script": "src/x.py", "prazo_s": 1500})
    os.makedirs(os.path.join(tp.L.raiz, "supervisor"), exist_ok=True)
    json.dump({"motivo": "guarda_alterada"}, open(os.path.join(tp.L.raiz, "supervisor", "PAUSA"), "w"))
    _, p = _passagem_outro_processo(tp.L, T0 + 30 * 60)
    assert p["esperas_ativas"][0]["tipo"] == "corrida" and p["bloqueios"]["pausa"]["motivo"] == "guarda_alterada", p


# ---------- rotação ----------
def _cenario_rotacao(nome):
    tp = Tempo(nome)
    tp.modelo("f2", "PC_19", falhos=("deriva_xy", "pes_no_chao"))
    tp.modelo("f1", "PC_19", falhos=("deriva_xy",))
    tp.modelo("ok", "PC_20")
    for m in (0, 5, 10):
        tp.em(m, "f2")       # antigos, antes do progresso: arquiváveis
    tp.em(20, "f1")          # progresso (melhora) — fica
    tp.em(25, "f1")          # depois do progresso — fica (janela do detector)
    tp.em(26, "f1")          # repetição -> disparo atual — fica
    return tp


def _estado(tp):
    itens = E.carregar_historico(tp.L.rel, tp.L.exp)
    res = {}
    for linha in ("L", "*"):
        e = E.avaliar_sessao(itens) if linha == "*" else E.avaliar(itens, linha)
        res[linha] = (e["emperrado"], e["degrau"], (e["ultimo_disparo"] or {}).get("evidencia"), e["esperando"])
    return res


@caso("rotação arquiva só o que a política permite e o estado do detector não muda")
def ro_politica():
    tp = _cenario_rotacao("ro1")
    antes = _estado(tp)
    n_antes = len(os.listdir(tp.L.rel))
    r = R.arquivar(time.time(), dias=1 / 24, pasta_rel=tp.L.rel, pasta_exp=tp.L.exp,
                   pasta_arquivo=os.path.join(tp.L.raiz, "relatorios_arquivo"), pasta_licoes=os.path.join(tp.L.raiz, "licoes"))
    assert len(r["arquivados"]) == 3, r
    assert len(os.listdir(tp.L.rel)) == n_antes - 3
    assert _estado(tp) == antes, (antes, _estado(tp))


@caso("rotação respeita experimento aberto e lição sem voto (protegidos com motivo)")
def ro_protecoes():
    tp = _cenario_rotacao("ro2")
    tp.k += 1
    json.dump(dict(tp.modelos["f2"], id="20261006-120000-1-1", quando_ts=E._quando_do_id("20261006-120000-1-1")),
              open(os.path.join(tp.L.rel, "20261006-120000-1-1.json"), "w", encoding="utf-8"))
    X.iniciar("ro-aberto", "experimento", "experimento aberto que cita um relatório", hipoteses=[B2.H_A, B2.H_B],
              sandbox=B2.SB, pasta=tp.L.exp)
    X.rodar("ro-aberto", "src/ok.py", pasta=tp.L.exp)  # a saída cita relatorio_id 20261006-120000-1-1
    RS.registrar_uso_licao("L-ver-01", "L", os.path.join(tp.L.raiz, "licoes"), agora=T0 + 4 * 60)
    r = R.arquivar(time.time(), dias=1 / 24, pasta_rel=tp.L.rel, pasta_exp=tp.L.exp,
                   pasta_arquivo=os.path.join(tp.L.raiz, "relatorios_arquivo"), pasta_licoes=os.path.join(tp.L.raiz, "licoes"))
    assert any("experimento aberto" in m for m in r["protegidos"]["20261006-120000-1-1"]), r["protegidos"]
    assert any("lição sem voto" in m for v in r["protegidos"].values() for m in v), r["protegidos"]
    assert len(r["arquivados"]) == 1, r["arquivados"]  # só o minuto 0 (antes da aplicação da lição)


@caso("depois da rotação: votos corretos, regressão rastreável (índice) e nenhum relatório some (lê do arquivo)")
def ro_rastreio():
    tp = _cenario_rotacao("ro3")
    pl = os.path.join(tp.L.raiz, "licoes")
    RS.registrar_uso_licao("L-ver-01", "L", pl, agora=T0 + 15 * 60)
    v_antes = RS.atualizar_votos(E.carregar_historico(tp.L.rel, tp.L.exp), pl)
    ids_antes = sorted(f[:-5] for f in os.listdir(tp.L.rel))
    arq = os.path.join(tp.L.raiz, "relatorios_arquivo")
    r = R.arquivar(time.time(), dias=1 / 24, pasta_rel=tp.L.rel, pasta_exp=tp.L.exp, pasta_arquivo=arq, pasta_licoes=pl)
    v_depois = RS.atualizar_votos(E.carregar_historico(tp.L.rel, tp.L.exp), pl)
    assert v_depois["L-ver-01"] == v_antes["L-ver-01"] == {"positivos": 1, "negativos": 0}, (v_antes, v_depois)
    ativos = sorted(f[:-5] for f in os.listdir(tp.L.rel))
    assert sorted(ativos + r["arquivados"]) == ids_antes
    orig = diario.PASTA_RELATORIOS
    diario.PASTA_RELATORIOS = tp.L.rel
    try:
        for rid in r["arquivados"]:
            assert diario.carregar_relatorio(rid)["id"] == rid
    finally:
        diario.PASTA_RELATORIOS = orig
    conh = D.resultados_conhecidos(tp.L.rel, os.path.join(arq, "indice.jsonl"))
    caso_c = {"id": "C1", "tipo": "contrato", "macro": "_fx", "args": ["PC_19"], "kwargs": {"falhos": ["deriva_xy", "pes_no_chao"]}}
    assert D.montar_fila([caso_c], M.versao_codigo(), conh)["contrato_em_dia"], "regressão perdeu o resultado arquivado"


# ---------- integração final ----------
@caso("INTEGRAÇÃO: pedido -> capacidade -> fila -> tentativas -> degrau -> supervisor -> lição -> nova estratégia -> relógio renovado -> nova sessão continua")
def i_longo():
    tp = Tempo("int4")
    ses, lic, sup = os.path.join(tp.L.raiz, "sessao"), os.path.join(tp.L.raiz, "licoes"), os.path.join(tp.L.raiz, "supervisor")
    assert D.atendibilidade("P02")["situacao"] == "atendivel"
    SS.definir_objetivo("P02: personagem conversando parado sem falso reprovado", "P02", ses)
    caso_e = {"id": "E-P02", "tipo": "exploracao", "macro": "_fx", "args": ["PC_22"], "kwargs": {}, "pedido": "P02"}
    fila = D.montar_fila([caso_e], M.versao_codigo(), D.resultados_conhecidos(tp.L.rel, os.path.join(tp.L.raiz, "x.jsonl")))
    assert fila["fila"][0]["motivo"] == "informacao_nova"
    tp.modelo("deriva", "PC_22", falhos=("deriva_xy",))
    tp.modelo("ok", "PC_22")
    tp.em(0, "deriva")
    tp.em(5, "deriva")                                   # repetição sem progresso
    estado = E.avaliar(E.carregar_historico(tp.L.rel, tp.L.exp), "L")
    assert estado["degrau"] == "cutucar"
    s1 = S.avaliar(T0 + 6 * 60, tp.L.rel, tp.L.exp, trava_path=os.path.join(tp.L.raiz, "n.trava"), pasta_sup=sup)
    assert s1["ultimo_progresso"]["tipo"] == "degrau:cutucar"
    o = RS.orientar(estado, lic)
    assert o["tipo_falha"] == "verificacao" and o["licoes"][0]["id"] == "L-ver-01"
    RS.registrar_uso_licao("L-ver-01", "L", lic, agora=T0 + 7 * 60)
    tp.em(10, "ok")                                      # nova estratégia: resultado melhor
    s2 = S.avaliar(T0 + 12 * 60, tp.L.rel, tp.L.exp, trava_path=os.path.join(tp.L.raiz, "n.trava"), pasta_sup=sup)
    assert s2["sem_progresso_min"] == 2.0 and not s2["alarmes"], s2
    assert RS.atualizar_votos(E.carregar_historico(tp.L.rel, tp.L.exp), lic)["L-ver-01"] == {"positivos": 1, "negativos": 0}
    cod = PASSAGEM.format(aqui=AQUI, agora=T0 + 13 * 60, rel=tp.L.rel, exp=tp.L.exp, ses=ses,
                          trava=os.path.join(tp.L.raiz, "n.trava"), sup=sup, lic=lic)
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", cod], capture_output=True, text=True, encoding="utf-8")
    p = json.loads([l for l in r.stdout.splitlines() if l.startswith("PASSAGEM ")][0][9:])
    assert p["objetivo"]["pedido"] == "P02" and p["ultimo_progresso"]["tipo"] in ("melhora_medida", "resultado_novo")
    assert p["sem_progresso_min"] == 3.0 and p["degrau_sessao"] is None and not p["pendencias"]["alarmes"], p


SECAO_SESSAO = [se_recupera, se_pequena, se_licoes, se_bloqueio]
SECAO_ROTACAO = [ro_politica, ro_protecoes, ro_rastreio]
SECAO_INTEGRACAO = [i_longo]

if __name__ == "__main__":
    B2._montar_sandbox()
    T4.rodar(SECAO_SESSAO + SECAO_ROTACAO + SECAO_INTEGRACAO, "bloco4-sessao")
