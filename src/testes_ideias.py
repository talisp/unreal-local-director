"""Testes do tools/conferir_ideias.py (linha 1, Fase 9), SEM Unreal: um arquivo bom passa; cada defeito reprova."""
import importlib.util
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from testes_v003_bloco1 import caso, rodar  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("conferir_ideias", os.path.join(RAIZ, "tools", "conferir_ideias.py"))
assert _spec and _spec.loader
CI = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(CI)
PACOTES = {"hypothesis": {"6.168.5"}, "pytest": {"9.1.1"}}  # fixo: o teste não depende do pip freeze da máquina

BOA = """# Ideias: trocas (08/10)
## 1. Medir o salto do pé na troca
- **Problema:** o pé escorrega na troca Victory -> Catwalk.
- **Ideia:** acrescentar o deslocamento do dedo do pé à nota da troca.
- **Evidência:** `src/unreal_macros/fila.py:100`
- **Custo:** baixo

## 2. Propriedade para a troca
- **Problema:** o recálculo das trocas não tem propriedade Hypothesis.
- **Ideia:** gerar ossos aleatórios e conferir que a nota nunca é negativa.
- **Evidência:** 138 trocas
- **Biblioteca:** hypothesis==6.168.5 — "st.floats(allow_nan=False)"
- **Fonte:** https://hypothesis.readthedocs.io/en/latest/ — "Hypothesis is a library for property-based testing"
- **Custo:** médio
"""


def _conf(texto):
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "ideias.md")
        open(p, "w", encoding="utf-8").write(texto)
        return CI.conferir(p, PACOTES)


@caso("arquivo no formato, com evidência que existe e versão instalada, passa")
def t_boa():
    r = _conf(BOA)
    assert r["ok"] and len(r["ideias"]) == 2, r


@caso("cada defeito reprova com o motivo (campo faltando, arquivo:linha inexistente, fonte sem trecho, sem versão)")
def t_defeitos():
    casos = {
        "falta 'Evidência'": BOA.replace("- **Evidência:** `src/unreal_macros/fila.py:100`\n", ""),
        "arquivo inexistente": BOA.replace("fila.py:100", "nao_existe.py:3"),
        "linha inexistente": BOA.replace("fila.py:100", "fila.py:999999"),
        "sem link http(s) e trecho": BOA.replace(' — "Hypothesis is a library for property-based testing"', ""),
        "sem versão citada": BOA.replace("hypothesis==6.168.5", "hypothesis"),
        "não está instalado": BOA.replace("hypothesis==6.168.5", "hypothesis==1.0.0"),
        "sem arquivo:linha nem número": BOA.replace("138 trocas", "muitas trocas"),
    }
    for motivo, texto in casos.items():
        r = _conf(texto)
        achados = [m for i in r["ideias"] for m in i["motivos"]]
        assert not r["ok"] and any(motivo in m for m in achados), (motivo, achados)


@caso("mais de 5 ideias reprova; arquivo sem ideia reprova")
def t_quantidade():
    uma = BOA.split("## 2.")[0].split("## 1.")[1]
    seis = "# Ideias\n" + "".join(f"## {i}. Ideia {i}{uma.split(chr(10), 1)[1]}" for i in range(1, 7))
    r = _conf(seis)
    assert not r["ok"] and any("máximo" in m for m in r["motivos"]), r["motivos"]
    assert not _conf("# nada aqui\n")["ok"]


@caso("ideia repetida de uma pendência aberta é recusada")
def t_repetida():
    texto = BOA.replace("## 1. Medir o salto do pé na troca", "## 1. Prova ao vivo da vigia relançando")
    texto = texto.replace("acrescentar o deslocamento do dedo do pé à nota da troca.",
                          "Prova ao vivo da vigia relançando depois de uma parada no limite de chamadas")
    r = _conf(texto)
    assert any("repetida da pendência" in m for m in r["ideias"][0]["motivos"]), r["ideias"][0]


if __name__ == "__main__":
    sys.exit(0 if rodar([t_boa, t_defeitos, t_quantidade, t_repetida], "ideias") else 1)
