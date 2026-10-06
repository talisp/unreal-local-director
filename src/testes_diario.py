"""Testes do diario.registrar_tentativa com relatórios reais capturados na bancada (06/10)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unreal_macros import diario  # noqa: E402

# relatório REAL do plateia_em_loop (PC_21, Talking_3, rodada 3, 08:0x — transcript da sessão)
REL_PASS = json.loads(r"""
{"ok": true, "medidas": {"atores": [{"ator": "PC_21_Mezz04", "clipe": "Talking_3", "tentativas": [{"clipe": "Talking_3",
 "passou": true, "gates": [
  {"nome": "silhueta_de_pe", "resultado": "PASS", "valor": {"altura_cm": 177.4, "largura_cm": 72.7}, "limite": "altura 160-210 cm, não deitado"},
  {"nome": "pes_no_chao", "resultado": "PASS", "valor": -2.5, "limite": "|gap| <= 4.0 cm"},
  {"nome": "ator_parado", "resultado": "PASS", "valor": {"desloc_cm": 0, "rot_graus": 0.0, "ajuste_z_declarado": 0.0}, "limite": "<= 0.5"},
  {"nome": "deriva_xy", "resultado": "PASS", "valor": 10.1, "limite": "<= 15.0 cm"},
  {"nome": "pes_plantados", "resultado": "PASS", "valor": 0.719, "limite": "IoU pernas >= 0.55"},
  {"nome": "distancia_vizinhos", "resultado": "PASS", "valor": [{"com": "SkeletalMeshActor_19", "dist_cm": 82.5}], "limite": ">= 45.0 cm"}],
 "bloqueio": null, "ajuste_z": 0.0}]}], "feitos": 1},
 "evidencias": [], "avisos": [], "bloqueio": null, "contexto": {}, "chamadas": 558, "segundos": 192.6}
""")

# relatório REAL de FAIL (PC_22, Hands_Forward_Gesture)
REL_FAIL = json.loads(r"""
{"ok": false, "medidas": {"atores": [{"ator": "PC_22_Mezz05", "clipe": null, "tentativas": [{"clipe": "Hands_Forward_Gesture",
 "passou": false, "gates": [
  {"nome": "silhueta_de_pe", "resultado": "PASS", "valor": {"altura_cm": 178.7, "largura_cm": 36.5}, "limite": "altura 160-210 cm, não deitado"},
  {"nome": "deriva_xy", "resultado": "FAIL", "valor": 16.8, "limite": "<= 15.0 cm"},
  {"nome": "pes_plantados", "resultado": "PASS", "valor": 0.838, "limite": "IoU pernas >= 0.55"}],
 "bloqueio": null, "ajuste_z": 4.4}]}], "feitos": 0},
 "bloqueio": "nenhum clipe passou para PC_22_Mezz05", "chamadas": 603, "segundos": 183.4}
""")


def testa_pass(tmp):
    linha = diario.linha_do_relatorio(REL_PASS, macro="plateia_em_loop", ator="PC_21_Mezz04",
                                      clipe="Talking_3 (loop)", rodada=3, tema="conversa_plateia",
                                      caso="conversa-3/10", previsao="passa", restaurado=False,
                                      restauracao="PASS fica aplicado (semântica plateia)")
    assert linha["ok"] is True
    assert linha["segundos"] == 192.6 and linha["chamadas"] == 558
    assert linha["gates"]["deriva_xy"] == "PASS (10.1)"
    assert linha["gates"]["silhueta_de_pe"] == "PASS (177.4/72.7)"
    assert "82.5" in linha["gates"]["distancia_vizinhos"]
    r = diario.registrar(REL_PASS, tmp, macro="plateia_em_loop", ator="PC_21_Mezz04", clipe="Talking_3",
                         rodada=3, tema="t", caso="c")
    assert r["ok"]
    gravado = json.loads(open(os.path.join(tmp, "diario.jsonl"), encoding="utf-8").read().strip())
    assert gravado["segundos"] == 192.6 and gravado["gates"]["pes_plantados"] == "PASS (0.719)"


def testa_fail(tmp):
    linha = diario.linha_do_relatorio(REL_FAIL, macro="plateia_em_loop", ator="PC_22_Mezz05",
                                      clipe="Hands_Forward_Gesture", rodada=3, tema="conversa_plateia")
    assert linha["ok"] is False
    assert linha["gates"]["deriva_xy"] == "FAIL (16.8)"
    assert linha["bloqueio"] == "nenhum clipe passou para PC_22_Mezz05"
    assert linha["macro"] == "plateia_em_loop" and linha["tipo"] == "tentativa"


def testa_omitir_vazios(tmp):
    rel = {"ok": False, "medidas": {}, "bloqueio": "gate reprovado: X", "segundos": 3.0, "chamadas": 5}
    linha = diario.linha_do_relatorio(rel, macro="medir_personagem", ator="A")
    assert "gates" not in linha and "rodada" not in linha and linha["gates"] if False else True
    assert linha == {"tipo": "tentativa", "hora": linha["hora"], "ator": "A", "macro": "medir_personagem",
                     "ok": False, "bloqueio": "gate reprovado: X", "segundos": 3.0, "chamadas": 5}


if __name__ == "__main__":
    import tempfile
    for fn in (testa_pass, testa_fail, testa_omitir_vazios):
        with tempfile.TemporaryDirectory() as tmp:
            fn(tmp)
        print("OK", fn.__name__)
    print("diario: 3/3")
