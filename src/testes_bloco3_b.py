"""v0.0.2 Bloco 3 — seções 2 (skill/orientação), 3 (lições/fontes) e integração do bloco completo. SEM Unreal.
Usa as mesmas fixtures reais de testes_bloco3 (envelope real das macros, controlador real com sandbox git falso)."""
import inspect
import json
import os
import subprocess
import sys
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import testes_bloco3 as T3  # noqa: E402
from testes_bloco3 import B2, E, X, Linha, caso, resultados  # noqa: E402
from unreal_macros import resolver as RS  # noqa: E402

TMP = T3.TMP


def _orientar(L, linha="L"):
    return RS.orientar(L.avaliar(linha), os.path.join(L.raiz, "licoes"))


# ---------- seção 2: skill / orientação ----------
@caso("cada classe de emperramento aponta o tipo de falha, o contorno e a seção/degrau esperados")
def s_mapa():
    casos = []
    L = Linha("m-gate")
    L.macro("PC_19", falhos=("deriva_xy",))
    L.macro("PC_19", falhos=("deriva_xy",))
    casos.append(("gate", L, "L", "repeticao", "verificacao"))
    L = Linha("m-cap")
    L.macro("Walking_X", erro=FileNotFoundError("sem clipe"))
    L.macro("Stairs_X", erro=FileNotFoundError("sem clipe"))
    casos.append(("capacidade", L, "L", "mesmo_erro", "capacidade"))
    L = Linha("m-amb")
    L.macro("PC_19", erro=TimeoutError("lento"))
    L.macro("PC_20", erro=TimeoutError("lento"))
    casos.append(("ambiente", L, "L", "mesmo_erro", "ambiente"))
    L = Linha("m-est")
    for i, err in enumerate((ValueError("x"), KeyError("y"), TypeError("z"))):
        L.macro(f"a{i}", erro=err)
    casos.append(("estagnacao", L, "L", "estagnacao", "estrategia"))
    L = Linha("m-dep")
    for _ in range(2):  # o agente tenta a MESMA linha com a dependência não integrada: duas recusas iguais
        try:
            X.iniciar("dep", "experimento", "linha que depende de branch solta", hipoteses=[B2.H_A, B2.H_B],
                      dependencias=["exp/solta"], sandbox=B2.SB, pasta=L.exp)
        except X.Recusa:
            pass
    casos.append(("dependencia", L, "dep", "repeticao", "dependencia"))
    for chave, L, linha, tipo_emp, tipo_falha in casos:
        o = _orientar(L, linha)
        assert o["emperrado"] and o["tipo_emperramento"] == tipo_emp and o["tipo_falha"] == tipo_falha, (chave, o)
        assert o["secao_skill"] == f"degrau:{o['degrau']}" and o["contorno"] == RS.CONTORNOS[tipo_falha], (chave, o)


@caso("recusa por dependência não integrada é classificada como 'dependencia' (tabela fixa)")
def s_dependencia():
    d = {"tipo": "mesmo_erro", "erro": "recusa:iniciar", "acao": "recusa:iniciar",
         "assinaturas": ['["recusa:iniciar","dependência \'exp/solta\' ainda NÃO está integrada no master"]']}
    assert RS.classificar(d) == "dependencia"
    assert RS.classificar(dict(d, assinaturas=['["recusa:rodar","limite de # corridas atingido"]'], erro="recusa:rodar")) == "estrategia"
    assert RS.classificar(dict(d, assinaturas=['["recusa:rodar","guarda.py da cópia foi ALTERADA"]'], erro="recusa:rodar")) == "ambiente"


@caso("a skill usa o degrau do detector sem refazer a detecção")
def s_nao_recalcula():
    L = Linha("norecalc")
    L.macro("PC_19", falhos=("deriva_xy",))
    L.macro("PC_19", falhos=("deriva_xy",))
    estado = L.avaliar()
    orig = E._regras
    E._regras = lambda h: (_ for _ in ()).throw(AssertionError("orientar recalculou a detecção"))
    try:
        o = RS.orientar(estado, os.path.join(L.raiz, "licoes"))
    finally:
        E._regras = orig
    assert o["degrau"] == estado["degrau"] == "cutucar"


@caso("a skill não transforma texto livre em progresso (sem porta para isso; usar lição não muda o estado)")
def s_sem_texto():
    srv = __import__("server")
    assert list(inspect.signature(srv.consultar_emperramento).parameters) == ["linha"]
    assert set(inspect.signature(RS.orientar).parameters) == {"estado", "pasta_licoes"}
    L = Linha("semtexto")
    L.macro("PC_19", falhos=("deriva_xy",))
    L.macro("PC_19", falhos=("deriva_xy",))
    antes = L.avaliar()
    RS.registrar_uso_licao("L-ver-01", "L", os.path.join(L.raiz, "licoes"))
    assert L.avaliar()["disparos"] == antes["disparos"]


@caso("SKILL.md curta e operacional, com os 5 degraus, as regras e a fonte reservada")
def s_doc():
    txt = open(os.path.join(AQUI, "..", "docs", "skills", "resolver-problemas", "SKILL.md"), encoding="utf-8").read()
    assert len(txt.splitlines()) <= 60, len(txt.splitlines())
    for termo in ("consultar_emperramento", "cutucar", "replanejar", "outro_caminho", "escalar", "abortar",
                  "tipo=conserto", "2–3 hipóteses", "3d-asset-server", "registrar_uso_licao"):
        assert termo in txt, termo


# ---------- seção 3: lições e fontes ----------
@caso("consulta de lições devolve só o subconjunto relevante (mesmo tipo, até 3); tipo sem lição = vazio")
def l_relevantes():
    p = os.path.join(TMP, "lic-rel")
    dep = RS.consultar_licoes("dependencia", "experimento depende de branch não integrada merge", p)
    assert [l["id"] for l in dep] == ["L-dep-01"], dep
    ver = RS.consultar_licoes("verificacao", "gate deriva_xy reprova conversa parada pernas plantadas", p)
    assert ver and len(ver) <= 3 and all(l["tipo_falha"] == "verificacao" for l in ver) and ver[0]["id"] == "L-ver-01", ver
    assert RS.consultar_licoes("entendimento", "qualquer coisa", p) == []
    assert len(RS._livro(p)) > 3


VOTO = """
import sys, os, json
sys.path.insert(0, {aqui!r})
import testes_bloco3 as T3
from unreal_macros import emperramento as E, resolver as RS
L = T3.Linha({nome!r})
pl = os.path.join(L.raiz, "licoes")
acao = {acao!r}
if acao == "usar":
    RS.registrar_uso_licao("L-ver-01", "L", pl)
elif acao == "melhorar":
    L.macro("PC_19", falhos=("deriva_xy",))
elif acao == "piorar":
    L.macro("PC_19", falhos=("deriva_xy", "pes_no_chao"))
    L.macro("PC_19", falhos=("deriva_xy", "pes_no_chao"))
elif acao == "votar":
    RS.atualizar_votos(E.carregar_historico(L.rel, L.exp), pl)
print("VOTOS " + json.dumps(RS.carregar_votos(pl).get("L-ver-01", {{}})))
"""


def _proc(nome, acao):
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", VOTO.format(aqui=AQUI, nome=nome, acao=acao)],
                       capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, ULD_TMP_B3=TMP))
    linha = [l for l in r.stdout.splitlines() if l.startswith("VOTOS ")]
    assert linha, r.stderr[-800:]
    return json.loads(linha[0][6:])


@caso("votos persistem entre processos e só mudam por evento do detector (progresso +1, disparo −1)")
def l_votos():
    nome = "votos"
    L = Linha(nome)
    L.macro("PC_19", falhos=("deriva_xy", "pes_no_chao"))
    _proc(nome, "usar")
    time.sleep(1.1)
    _proc(nome, "melhorar")
    v = _proc(nome, "votar")
    assert v == {"positivos": 1, "negativos": 0}, v
    assert _proc(nome, "votar") == v
    _proc(nome, "usar")
    time.sleep(1.1)
    _proc(nome, "piorar")
    assert _proc(nome, "votar") == {"positivos": 1, "negativos": 1}


@caso("fonte NÃO instalada nunca aparece como disponível; registro tem 3d-asset-server = não instalado")
def f_fontes():
    reg = json.load(open(RS.FONTES, encoding="utf-8"))
    a3 = [f for f in reg["objeto_3d"] if "3d-asset-server" in f["nome"]]
    assert a3 and a3[0]["status"] == "nao_instalado"
    r = RS.consultar_fontes(["objeto_3d", "movimento", "codigo", "unreal"])
    assert all(f["status"] == "instalado" for f in r["disponiveis"])
    assert any("3d-asset-server" in f["nome"] for f in r["reservadas"])
    assert not any("3d-asset-server" in f["nome"] for f in r["disponiveis"])
    so3d = RS.consultar_fontes(["objeto_3d"])
    assert so3d["disponiveis"] == [] and len(so3d["reservadas"]) == 2


@caso("capacidade faltando: a skill recebe as fontes e só pode construir do zero se nenhuma estiver disponível")
def f_capacidade():
    L = Linha("cap-fontes")
    L.macro("Walking_X", erro=FileNotFoundError("sem clipe"))
    L.macro("Stairs_X", erro=FileNotFoundError("sem clipe"))
    o = _orientar(L)
    assert o["tipo_falha"] == "capacidade" and o["fontes"]["disponiveis"] and o["construir_do_zero_permitido"] is False, o


# ---------- integração do bloco completo ----------
@caso("INTEGRAÇÃO: experimento -> corridas iguais -> detector -> degrau -> skill -> lições -> persistido -> outro processo lê")
def i_fluxo():
    L = Linha("int")
    X.iniciar("int-exp", "experimento", "integração completa do bloco 3", hipoteses=[B2.H_A, B2.H_B], sandbox=B2.SB, pasta=L.exp)
    X.rodar("int-exp", "src/falha.py", pasta=L.exp)
    assert not L.avaliar("int-exp")["emperrado"]
    X.rodar("int-exp", "src/falha.py", pasta=L.exp)
    estado = L.avaliar("int-exp")
    o = RS.orientar(estado, os.path.join(L.raiz, "licoes"))
    assert o["emperrado"] and o["degrau"] == "cutucar" and o["tipo_falha"] == "estrategia", o
    assert [l["id"] for l in o["licoes"]] == ["L-est-01"], o["licoes"]
    arq = os.path.join(L.raiz, "emperramento", "disparos.jsonl")
    E.registrar_disparos(estado, arq)
    cod = (f"import sys, json; sys.path.insert(0, {AQUI!r}); from unreal_macros import emperramento as E; "
           f"e = E.avaliar(E.carregar_historico({L.rel!r}, {L.exp!r}), 'int-exp'); "
           f"print('ESTADO ' + json.dumps({{'degrau': e['degrau'], 'emperrado': e['emperrado']}}))")
    r = subprocess.run([sys.executable, "-X", "utf8", "-c", cod], capture_output=True, text=True, encoding="utf-8")
    outro = json.loads([l for l in r.stdout.splitlines() if l.startswith("ESTADO ")][0][7:])
    assert outro == {"degrau": "cutucar", "emperrado": True}, outro
    E.registrar_disparos(L.avaliar("int-exp"), arq)
    assert len(open(arq, encoding="utf-8").read().strip().splitlines()) == 1


@caso("CONTROLE NEGATIVO: espera declarada (corrida longa) -> resultado novo -> NÃO declara emperramento")
def i_controle():
    L = Linha("int-neg")
    X.iniciar("neg-exp", "experimento", "controle negativo do bloco 3", hipoteses=[B2.H_A, B2.H_B], sandbox=B2.SB, pasta=L.exp)
    th = threading.Thread(target=X.rodar, args=("neg-exp", "src/lento.py"), kwargs={"pasta": L.exp})
    th.start()
    time.sleep(2)
    meio = L.avaliar("neg-exp")
    th.join()
    X.rodar("neg-exp", "src/ok.py", pasta=L.exp)
    fim = RS.orientar(L.avaliar("neg-exp"), os.path.join(L.raiz, "licoes"))
    assert meio["esperando"] == [1] and not meio["disparos"], meio
    assert not fim["emperrado"] and fim["degrau"] is None, fim


if __name__ == "__main__":
    B2._montar_sandbox()
    for fn in (s_mapa, s_dependencia, s_nao_recalcula, s_sem_texto, s_doc, l_relevantes, l_votos, f_fontes, f_capacidade,
               i_fluxo, i_controle):
        fn()
    for nome, ok, msg in resultados:
        print(("OK   " if ok else "FALHA") + " " + nome + (f" | {msg}" if msg else ""))
    print(f"bloco3b: {sum(ok for _, ok, _ in resultados)}/{len(resultados)}")
    sys.exit(0 if resultados and all(ok for _, ok, _ in resultados) else 1)  # 0/0 é falha
