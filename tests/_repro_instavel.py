"""Reproduz a instabilidade da 1a medida (Astra): aplicar e medir 3x seguidas, sem mudar nada."""
import testes_contrato as T
from unreal_macros import macros as M
T.limpar()
T.c.call(T.SCENE, "add_to_scene_from_asset", asset_path="/Engine/BasicShapes/Cube.Cube", name="TESTE_PISO",
         xform=T.xform(T.ZX, 0, -50, s=(12, 12, 1)))
T.boneco("TESTE_BONECO_A", T.ZX, 0)
r = M.aplicar_clipe("TESTE_BONECO_A", "Thoughtful_Head_Nod", loop=True)
print("aplicar", r["ok"], r["bloqueio"], r["medidas"].get("silhueta", {}).get("gap_local_cm"), r["segundos"])
for i in range(5):
    m = M.medir_personagem("TESTE_BONECO_A", com_vizinhos=False)
    s = m["medidas"]["silhueta"]
    print("medir", i, m["ok"], s.get("gap_local_cm"), s.get("altura_cm"), s.get("area_pernas_cm2"), s.get("observacoes_gap"), m["segundos"])
T.limpar()
