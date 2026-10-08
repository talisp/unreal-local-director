"""v0.0.2 Bloco 1 — testes SEM o Unreal (cliente falso). Os testes no Unreal ficam para o Bloco 5.

1. deriva pelas pernas (exp2): gesticular parado passa; andar reprova; o gate antigo reprovaria o gesticular.
2. comportamento padrão preservado: com a captura estável DESLIGADA, a sequência de chamadas ao Unreal de
   _silhueta é idêntica à da produção (main); ligada, muda (prova de que a chave funciona).
3. relatório com id (registrar_tentativa): a macro grava o relatório; a linha sai do disco (fonte relatorio_id);
   JSON colado fica marcado "colado"; id malicioso é recusado; a ferramenta não aceita diretório do agente.
"""
import base64
import importlib
import inspect
import io
import json
import os
import subprocess
import sys
import tempfile

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
PROD = os.environ.get("ULD_PROD_SRC", os.path.join(os.path.expanduser("~"), "unreal-macros", "src"))
sys.path.insert(0, AQUI)
resultados = []


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


# ---------- 1. deriva pelas pernas ----------
def _amostra(desloc_pernas_px: float, desloc_tronco_px: float, larg=200, alt=160, base=100.0, ppc=2.0):
    m = np.zeros((alt, larg), bool)
    x = int(base + desloc_pernas_px)
    m[80:, x - 6:x + 6] = True                       # pernas (região abaixo de 80 cm)
    centro_sil = (base + desloc_tronco_px - base) / ppc  # o que o gate antigo usava (silhueta inteira)
    return {"medido": True, "px_por_cm": ppc, "_rx_mean_px": base, "_pernas": m[80:, :],
            "centro_desvio_cm": round(centro_sil, 1), "altura_cm": 178.0, "gap_pes_cm": 0.0, "deitado": False}


@caso("deriva: gesticular parado (tronco balança 20 cm) PASSA; o gate antigo reprovaria")
def t_gesticular():
    from unreal_macros import gates, workflows as W
    lat = [_amostra(0, t) for t in (0, 40, -40, 20)]   # tronco ±20 cm, pernas paradas
    fr = [_amostra(0, t) for t in (0, 30, -30, 10)]
    orig = W.M._amostrar_estudio
    W.M._amostrar_estudio = lambda a, vista, n, intervalo: lat if vista == "lateral" else fr
    try:
        gs = {g["nome"]: g for g in W._gate_deriva({"refPath": "x"}, 15.0)}
    finally:
        W.M._amostrar_estudio = orig
    assert gs["deriva_xy"]["resultado"] == "PASS", gs["deriva_xy"]
    assert gs["pes_plantados"]["resultado"] == "PASS", gs["pes_plantados"]
    antigo = gates.deriva_xy([(s["centro_desvio_cm"], f["centro_desvio_cm"]) for s, f in zip(lat, fr)], 15.0)
    assert antigo["resultado"] == "FAIL", antigo  # é exatamente o falso-FAIL que o exp2 corrigiu


@caso("deriva: andar (pernas se deslocam 30 cm) REPROVA")
def t_andar():
    from unreal_macros import workflows as W
    lat = [_amostra(d, d) for d in (0, 20, 40, 60)]
    fr = [_amostra(0, 0) for _ in range(4)]
    orig = W.M._amostrar_estudio
    W.M._amostrar_estudio = lambda a, vista, n, intervalo: lat if vista == "lateral" else fr
    try:
        gs = {g["nome"]: g for g in W._gate_deriva({"refPath": "x"}, 15.0)}
    finally:
        W.M._amostrar_estudio = orig
    assert gs["deriva_xy"]["resultado"] == "FAIL", gs["deriva_xy"]


@caso("deriva: amostra sem máscara de pernas reprova com motivo (não passa por omissão)")
def t_sem_pernas():
    from unreal_macros import workflows as W
    ruim = dict(_amostra(0, 0))
    ruim.pop("_pernas")
    orig = W.M._amostrar_estudio
    W.M._amostrar_estudio = lambda a, vista, n, intervalo: [ruim] * 4
    try:
        gs = W._gate_deriva({"refPath": "x"}, 15.0)
    finally:
        W.M._amostrar_estudio = orig
    assert gs[0]["resultado"] == "FAIL" and "pernas não mensuráveis" in str(gs[0]["valor"]), gs


# ---------- 2. comportamento padrão preservado (sequência de chamadas) ----------
SONDA = r'''
import base64, io, json, os, sys
sys.path.insert(0, {src!r})
os.environ.pop("ULD_CAPTURA_ESTAVEL", None)
if {ligar!r}:
    os.environ["ULD_CAPTURA_ESTAVEL"] = "1"
import numpy as np
from PIL import Image
from unreal_macros import macros as M
buf = io.BytesIO(); Image.fromarray(np.zeros((90, 120, 3), "uint8")).save(buf, "PNG")
PNG = base64.b64encode(buf.getvalue()).decode()
seq = []
class Falso:
    log = []; prazo = None
    def call(self, ts, tool, **a):
        seq.append(tool); self.log.append((tool, 0, True))
        if tool == "get_actor_transform":
            return {{"location": {{"x": 0, "y": 0, "z": 0}}, "rotation": {{"pitch": 0, "yaw": 0, "roll": 0}}, "scale": {{"x": 1, "y": 1, "z": 1}}}}
        if tool == "get_properties":
            return json.dumps({{"relativeLocation": {{"x": 0, "y": 0, "z": 0}}, "relativeRotation": {{"pitch": 0, "yaw": 0, "roll": 0}}, "castShadow": True}})
        if tool == "get_root_component":
            return {{"refPath": "/Game/L.L:PersistentLevel.A.SkeletalMeshComponent0"}}
        if tool == "trace_world":
            return 150.0
        if tool == "WorldPosToScreenCoords":
            z = a["position"]["z"]; return {{"x": 0.5, "y": 0.9 - z / 400.0}}
        if tool == "CaptureViewport":
            return {{"image": {{"data": PNG}}}}
        return True
M._cliente = Falso()
M.cliente = lambda: M._cliente
M.time.sleep = lambda s: None
s = M._silhueta({{"refPath": "/Game/L.L:PersistentLevel.A"}})
print("SEQ " + json.dumps({{"seq": seq, "estab": "estabilidade" in s}}))
'''


def _sequencia(src, ligar=False):
    out = subprocess.run([sys.executable, "-X", "utf8", "-c", SONDA.format(src=src, ligar=ligar)],
                         capture_output=True, text=True, encoding="utf-8", timeout=120)
    linha = [l for l in out.stdout.splitlines() if l.startswith("SEQ ")]
    if not linha:
        raise RuntimeError(out.stderr[-1200:])
    return json.loads(linha[0][4:])


@caso("captura estável DESLIGADA: sequência de chamadas idêntica à produção (main)")
def t_padrao_igual():
    a, b = _sequencia(PROD), _sequencia(AQUI)
    assert a["seq"] == b["seq"], (len(a["seq"]), len(b["seq"]))
    assert not b["estab"]


@caso("captura estável LIGADA (ULD_CAPTURA_ESTAVEL=1): caminho novo é usado e declarado")
def t_ligada():
    b, c = _sequencia(AQUI), _sequencia(AQUI, ligar=True)
    assert c["estab"] and c["seq"] != b["seq"]


# ---------- 3. relatório com id ----------
@caso("macro grava relatório com id; registrar_tentativa lê do disco (fonte=relatorio_id) com os mesmos números")
def t_relatorio_id():
    from unreal_macros import catalogo, diario
    rel = catalogo.buscar_clipe("head nod", n=2)
    assert rel.get("id") and os.path.exists(os.path.join(diario.PASTA_RELATORIOS, rel["id"] + ".json")), rel.get("id")
    with tempfile.TemporaryDirectory() as tmp:
        r = diario.registrar(diario.carregar_relatorio(rel["id"]), tmp, macro="buscar_clipe", fonte="relatorio_id")
        assert r["linha"]["relatorio_id"] == rel["id"] and r["linha"]["fonte"] == "relatorio_id"
        assert r["linha"]["segundos"] == rel["segundos"] and r["linha"]["chamadas"] == rel["chamadas"]


@caso("id malicioso ou inexistente é recusado")
def t_id_ruim():
    from unreal_macros import diario
    for ruim in ("../../segredo", "", "x" * 200):
        try:
            diario.carregar_relatorio(ruim)
            raise AssertionError(f"aceitou {ruim!r}")
        except ValueError:
            pass
    try:
        diario.carregar_relatorio("20990101-000000-1-1")
        raise AssertionError("aceitou id inexistente")
    except FileNotFoundError:
        pass


@caso("ferramenta MCP registrar_tentativa: sem parâmetro de diretório; JSON colado marcado 'colado'")
def t_ferramenta():
    srv = importlib.import_module("server")
    params = inspect.signature(srv.registrar_tentativa).parameters
    assert "diretorio" not in params, list(params)
    from unreal_macros import diario
    with tempfile.TemporaryDirectory() as tmp:
        orig = diario.PASTA_DIARIO
        diario.PASTA_DIARIO = tmp
        try:
            out = json.loads(srv.registrar_tentativa(macro="medir_personagem", relatorio_json=json.dumps(
                {"ok": True, "medidas": {}, "segundos": 1.0, "chamadas": 2})))
            sem = json.loads(srv.registrar_tentativa(macro="medir_personagem"))
        finally:
            diario.PASTA_DIARIO = orig
    assert out["ok"] and out["linha"]["fonte"] == "colado", out
    assert sem["ok"] is False and "relatorio_id" in sem["bloqueio"], sem


if __name__ == "__main__":
    for fn in (t_gesticular, t_andar, t_sem_pernas, t_padrao_igual, t_ligada, t_relatorio_id, t_id_ruim, t_ferramenta):
        fn()
    for nome, ok, msg in resultados:
        print(("OK   " if ok else "FALHA") + " " + nome + (f" | {msg}" if msg else ""))
    print(f"bloco1: {sum(ok for _, ok, _ in resultados)}/{len(resultados)}")
    sys.exit(0 if resultados and all(ok for _, ok, _ in resultados) else 1)  # 0/0 é falha
