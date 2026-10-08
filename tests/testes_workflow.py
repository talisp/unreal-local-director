"""Teste do workflow plateia_em_loop e do cartão de cena na zona de testes (3 bonecos TESTE_*, nada é salvo)."""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from unreal_macros import cartao, workflows, macros as M  # noqa: E402
from unreal_macros.mcp_client import ACTOR, SCENE  # noqa: E402
from testes_contrato import boneco, limpar, xform, ZX  # noqa: E402

c = M.cliente()
res = []
limpar()
piso = c.call(SCENE, "add_to_scene_from_asset", asset_path="/Engine/BasicShapes/Cube.Cube", name="TESTE_PISO",
              xform=xform(ZX, 0, -50, s=(12, 12, 1)))
c.call(ACTOR, "set_label", actor=piso if isinstance(piso, dict) else {"refPath": piso}, label="TESTE_PISO")
for i, (x, yaw) in enumerate([(-120, 20), (0, 0), (120, -20)]):
    boneco(f"TESTE_PLATEIA_{i}", ZX + x, 0, yaw)
atores = [f"TESTE_PLATEIA_{i}" for i in range(3)]

r = workflows.plateia_em_loop(atores, candidatos=["Head_Nod_Yes", "Thoughtful_Head_Nod", "Arm_Gesture", "Talking_2"])
res.append({"teste": "plateia_em_loop 3 bonecos", "ok": r["ok"], "bloqueio": r["bloqueio"], "feitos": r["medidas"].get("feitos"),
            "atores": [{"ator": a["ator"], "clipe": a["clipe"], "tentativas": [(t["clipe"], t.get("passou")) for t in a["tentativas"]]}
                       for a in r["medidas"].get("atores", [])], "chamadas": r["chamadas"], "segundos": r["segundos"]})
print(json.dumps(res[-1], ensure_ascii=False, indent=0))

# Controle: só um candidato que anda (Walking) -> nenhum passa -> o workflow para no primeiro e restaura.
r2 = workflows.plateia_em_loop(["TESTE_PLATEIA_0"], candidatos=["Walking"])
res.append({"teste": "CONTROLE plateia só com Walking (anda) deve parar", "ok": r2["ok"], "bloqueio": r2["bloqueio"],
            "tentativas": [(t["clipe"], t.get("passou"), [g["nome"] for g in t.get("gates", []) if g["resultado"] != "PASS"])
                           for a in r2["medidas"].get("atores", []) for t in a["tentativas"]], "segundos": r2["segundos"]})
print(json.dumps(res[-1], ensure_ascii=False, indent=0))

cart = {"objetivo": "teste de cartão: medir e capturar um boneco", "deve_evitar": ["mover o ator"],
        "passos": [{"id": "m", "acao": "medir_personagem", "ator": "TESTE_PLATEIA_1"},
                   {"id": "f", "acao": "capturar_evidencia", "ator": "TESTE_PLATEIA_1", "depois": "m"}]}
r3 = cartao.executar_cartao(cart)
res.append({"teste": "executar_cartao medir+capturar", "ok": r3["ok"], "bloqueio": r3["bloqueio"], "evidencias": r3["evidencias"]})
print(json.dumps(res[-1], ensure_ascii=False))
limpar()
json.dump({"quando": dt.datetime.now().isoformat(timespec="minutes"), "resultados": res},
          open(os.path.join(os.path.dirname(__file__), "..", "work", "testes_workflow.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
# Esperado: plateia ok, controle (só Walking) PARA (ok=False), cartão ok.
passou = [res[0]["ok"] is True, res[1]["ok"] is False, res[2]["ok"] is True]
print(f"workflow: {sum(passou)}/{len(passou)}")
sys.exit(0 if all(passou) else 1)
