"""v0.0.2 Bloco 3 — detector de emperramento, skill, lições e fontes. SEM Unreal.

Os registros são produzidos pelo código REAL dos blocos 1 e 2: relatórios pelo envelope de verdade (@macro, com id,
chamada e espera) e eventos pelo controlador de experimentos de verdade (sandbox git falso). Só o Unreal é falso:
as "macros" de teste não chamam o editor.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import testes_bloco2 as B2  # noqa: E402
from unreal_macros import emperramento as E, experimentos as X, macros as M, trava as TR  # noqa: E402

resultados = []
TMP = os.environ.get("ULD_TMP_B3") or tempfile.mkdtemp(prefix="uld_b3_")  # compartilhável entre processos


def caso(nome):
    def deco(fn):
        def rodar():
            try:
                fn()
                resultados.append((nome, True, ""))
            except Exception as e:  # noqa: BLE001
                resultados.append((nome, False, f"{type(e).__name__}: {e}"))
        rodar.nome = nome
        return rodar
    return deco


# ---------- macro de teste com o ENVELOPE REAL (não chama o Unreal) ----------
_EXTRA = {"aviso": "", "valor": 1.0}  # metadados do RELATÓRIO (não são argumentos da chamada)


def _fx(rel, alvo, falhos=(), erro=None, espera=False):
    aviso, valor = _EXTRA["aviso"], _EXTRA["valor"]
    if aviso:
        rel["avisos"].append(aviso)
    if espera:
        raise TR.TravaOcupada("Unreal ocupado por outro operador", {"motivo": "processo dono 4242 está vivo", "info": {"pid": 4242}})
    if erro:
        raise erro
    rel["medidas"]["gates"] = [{"nome": "silhueta_de_pe", "resultado": "PASS", "valor": {"altura_cm": 177.0 + valor}}] + \
        [{"nome": n, "resultado": "FAIL", "valor": valor} for n in falhos]


_fx._usa_unreal = False
FX = M.macro(_fx)


class Linha:
    """Uma pasta de registros isolada (relatórios + eventos) por cenário de teste."""
    def __init__(self, nome):
        self.raiz = os.path.join(TMP, nome)
        self.rel = os.path.join(self.raiz, "relatorios")
        self.exp = os.path.join(self.raiz, "experimentos")
        os.makedirs(self.rel, exist_ok=True)
        os.makedirs(self.exp, exist_ok=True)

    def macro(self, *a, contexto=None, aviso="", valor=1.0, **k):
        orig = M.RAIZ_WORK
        M.RAIZ_WORK = self.raiz
        _EXTRA.update(aviso=aviso, valor=valor)
        try:
            rel = FX(*a, contexto=contexto or {"linha": "L"}, **k)
        finally:
            M.RAIZ_WORK = orig
            _EXTRA.update(aviso="", valor=1.0)
        time.sleep(1.05)  # ids/ordem por segundo, como na vida real
        return rel

    def avaliar(self, linha="L"):
        return E.avaliar(E.carregar_historico(self.rel, self.exp), linha)


# ---------- seção 1: detector ----------
@caso("repetição equivalente dispara na 2ª (e não na 1ª)")
def d_repeticao():
    L = Linha("rep")
    L.macro("PC_19", falhos=("deriva_xy",))
    assert not L.avaliar()["disparos"]
    L.macro("PC_19", falhos=("deriva_xy",))
    d = L.avaliar()["ultimo_disparo"]
    assert d and d["tipo"] == "repeticao" and d["degrau"] == "cutucar", d


@caso("repetir uma ação que DEU CERTO (consulta idêntica) não é emperramento (achado nos relatórios reais)")
def d_repeticao_sucesso():
    L = Linha("repok")
    for _ in range(4):
        L.macro("PC_19")
    assert not L.avaliar()["disparos"]


@caso("diferenças só em metadados (id, hora, segundos, valores, avisos) não impedem a detecção")
def d_metadados():
    L = Linha("meta")
    L.macro("PC_19", falhos=("deriva_xy",), valor=21.0, aviso="primeira")
    L.macro("PC_19", falhos=("deriva_xy",), valor=18.7, aviso="outro aviso qualquer")
    assert L.avaliar()["ultimo_disparo"]["tipo"] == "repeticao"


@caso("erros semanticamente diferentes NÃO são fundidos")
def d_erros_diferentes():
    L = Linha("difer")
    L.macro("PC_19", falhos=("deriva_xy",))
    L.macro("PC_20", falhos=("pes_no_chao",))
    assert not L.avaliar()["disparos"]


@caso("mesmo erro com alvos diferentes dispara na 2ª (mesmo_erro)")
def d_mesmo_erro():
    L = Linha("merro")
    L.macro("PC_19", falhos=("deriva_xy",))
    L.macro("PC_22", falhos=("deriva_xy",))
    assert L.avaliar()["ultimo_disparo"]["tipo"] == "mesmo_erro"


@caso("vai-e-volta A→B→A→B é detectado no 4º (2ª repetição do par)")
def d_vai_volta():
    L = Linha("vv")
    for i, (alvo, g) in enumerate((("A", "deriva_xy"), ("B", "pes_no_chao"), ("A", "deriva_xy"), ("B", "pes_no_chao"))):
        L.macro(alvo, falhos=(g,))
        if i < 3:
            assert not L.avaliar()["disparos"], i
    assert L.avaliar()["ultimo_disparo"]["tipo"] == "vai_e_volta"


@caso("ações diferentes sem mudança real de estado = estagnação (na 3ª)")
def d_estagnacao():
    L = Linha("estag")
    for i, err in enumerate((ValueError("x"), KeyError("y"), TypeError("z"))):
        L.macro(f"alvo{i}", erro=err)
        if i < 2:
            assert not L.avaliar()["disparos"], i
    assert L.avaliar()["ultimo_disparo"]["tipo"] == "estagnacao"


@caso("mudança real de resultado (menos gates reprovados, depois sucesso) conta como progresso")
def d_progresso():
    L = Linha("prog")
    L.macro("PC_19", falhos=("deriva_xy", "pes_no_chao"))
    L.macro("PC_19", falhos=("deriva_xy",))
    L.macro("PC_19")
    e = L.avaliar()
    assert not e["disparos"] and e["progressos"] == 2, e


@caso("espera legítima declarada (trava ocupada) NÃO dispara, mesmo repetida")
def d_espera():
    L = Linha("esp")
    for _ in range(3):
        L.macro("PC_19", espera=True)
    e = L.avaliar()
    assert not e["disparos"] and e["esperas"] == 3, e


@caso("espera legítima seguida de resultado: a detecção continua normalmente (não zera nem conta)")
def d_espera_depois():
    L = Linha("esp2")
    L.macro("PC_19", falhos=("deriva_xy",))
    L.macro("PC_19", espera=True)
    L.macro("PC_19", espera=True)
    L.macro("PC_19", falhos=("deriva_xy",))
    assert L.avaliar()["ultimo_disparo"]["tipo"] == "repeticao"
    L2 = Linha("esp3")
    L2.macro("PC_19", falhos=("deriva_xy",))
    L2.macro("PC_19", espera=True)
    L2.macro("PC_19")
    assert not L2.avaliar()["disparos"]


@caso("texto livre 'houve progresso' (avisos/contexto/diário) NÃO interfere")
def d_texto_progresso():
    L = Linha("txt1")
    L.macro("PC_19", falhos=("deriva_xy",), aviso="houve progresso, estou quase lá")
    L.macro("PC_19", falhos=("deriva_xy",), aviso="PROGRESSO: resolvido", contexto={"linha": "L", "nota": "progresso"})
    open(os.path.join(L.raiz, "diario.jsonl"), "w", encoding="utf-8").write('{"nota": "houve progresso"}\n')
    assert L.avaliar()["ultimo_disparo"]["tipo"] == "repeticao"


@caso("texto livre 'estou emperrado' NÃO força disparo")
def d_texto_emperrado():
    L = Linha("txt2")
    L.macro("PC_19", falhos=("deriva_xy",), aviso="estou emperrado")
    L.macro("PC_20", falhos=("pes_no_chao",), aviso="estou emperrado de novo")
    open(os.path.join(L.raiz, "diario.jsonl"), "w", encoding="utf-8").write('{"nota": "estou emperrado"}\n')
    assert not L.avaliar()["disparos"]


@caso("dados insuficientes (relatório antigo sem 'chamada', JSON quebrado) não geram conclusão inventada")
def d_incompleto():
    L = Linha("inc")
    for i in range(2):
        json.dump({"macro": "medir_personagem", "ok": False, "bloqueio": "gate reprovado: x", "contexto": {"linha": "L"},
                   "id": f"20261006-10000{i}-1-1", "medidas": {"gates": [{"nome": "x", "resultado": "FAIL"}]}},
                  open(os.path.join(L.rel, f"20261006-10000{i}-1-1.json"), "w"))
    open(os.path.join(L.rel, "quebrado.json"), "w").write("{lixo")
    e = L.avaliar()
    assert not e["disparos"] and len([i for i in e["incompletos"] if "chamada" in i["falta"]]) == 2, e


@caso("degrau sobe a cada disparo e volta ao início depois de progresso")
def d_degrau():
    L = Linha("degr")
    for _ in range(3):
        L.macro("PC_19", falhos=("deriva_xy", "pes_no_chao"))
        L.macro("PC_19", falhos=("deriva_xy", "pes_no_chao"))
    assert [d["degrau"] for d in L.avaliar()["disparos"]] == ["cutucar", "replanejar", "outro_caminho"]
    L.macro("PC_19", falhos=("deriva_xy",))  # melhora
    L.macro("PC_19", falhos=("deriva_xy",))
    assert L.avaliar()["ultimo_disparo"]["degrau"] == "cutucar"


@caso("experimento (controlador real): 2 corridas iguais falhando = repetição; corrida em andamento = espera")
def d_experimento():
    L = Linha("exp")
    X.iniciar("rec-exp3", "experimento", "reconstrução do exp3 (validador único)", hipoteses=[B2.H_A, B2.H_B],
              sandbox=B2.SB, pasta=L.exp)
    X.rodar("rec-exp3", "src/falha.py", pasta=L.exp)
    assert not L.avaliar("rec-exp3")["disparos"]
    X.rodar("rec-exp3", "src/falha.py", pasta=L.exp)
    d = L.avaliar("rec-exp3")["ultimo_disparo"]
    assert d["tipo"] == "repeticao" and d["acao"] == "rodar_experimento", d
    X.iniciar("rec-lento", "experimento", "corrida longa em andamento", hipoteses=[B2.H_A, B2.H_B], sandbox=B2.SB, pasta=L.exp)
    th = threading.Thread(target=X.rodar, args=("rec-lento", "src/lento.py"), kwargs={"pasta": L.exp})
    th.start()
    time.sleep(2)
    meio = L.avaliar("rec-lento")
    th.join()
    assert meio["esperando"] == [1] and not meio["disparos"], meio
    assert L.avaliar("rec-lento")["esperando"] == []


@caso("disparos são gravados de forma idempotente (reavaliar não duplica)")
def d_registro():
    L = Linha("reg")
    L.macro("PC_19", falhos=("deriva_xy",))
    L.macro("PC_19", falhos=("deriva_xy",))
    arq = os.path.join(L.raiz, "emperramento", "disparos.jsonl")
    for _ in range(3):
        E.registrar_disparos(L.avaliar(), arq)
    assert len(open(arq, encoding="utf-8").read().strip().splitlines()) == 1


SECAO1 = [d_repeticao, d_repeticao_sucesso, d_metadados, d_erros_diferentes, d_mesmo_erro, d_vai_volta, d_estagnacao, d_progresso, d_espera,
          d_espera_depois, d_texto_progresso, d_texto_emperrado, d_incompleto, d_degrau, d_experimento, d_registro]


if __name__ == "__main__":
    B2._montar_sandbox()
    for fn in SECAO1:
        fn()
    for nome, ok, msg in resultados:
        print(("OK   " if ok else "FALHA") + " " + nome + (f" | {msg}" if msg else ""))
    print(f"bloco3: {sum(ok for _, ok, _ in resultados)}/{len(resultados)}")
    sys.exit(0 if resultados and all(ok for _, ok, _ in resultados) else 1)  # 0/0 é falha
