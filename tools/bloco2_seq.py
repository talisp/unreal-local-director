"""v0.0.3 Bloco 2 — experimento A (Sequencer): bloco pronto "andar" = Start_Walking → Walking × n → Stop_Walking.
Evidência pedida (MAPA_LACUNAS_V.md): o boneco anda ~3+ m e para; nas trocas de clipe não há salto (quadril e
dedos contínuos); o avanço medido bate com o previsto; vídeo isolado gerado. Nada é salvo; tudo é desfeito no fim.
Uso: python tools/bloco2_seq.py [n_walking]"""
import json
import math
import os
import re
import sys

V003 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("UNREAL_MACROS_TRAVA", r"<repo>\work\unreal.trava")
sys.path.insert(0, os.path.join(V003, "src"))
os.chdir(os.path.join(V003, "src"))
import testes_contrato as TC  # noqa: E402
from unreal_macros import macros as M, trava  # noqa: E402
from unreal_macros.mcp_client import SCENE, SEQ  # noqa: E402

SAIDA = os.path.join(V003, "work", "bloco2")
os.makedirs(os.path.join(SAIDA, "quadros"), exist_ok=True)
FPS = 30
OSSOS = "Hips,LeftFoot,RightFoot,LeftToeBase,RightToeBase"


def nome():
    return max(re.findall(r"[\w.]*DirectorTools\w*", M.cliente().list_toolsets()), key=len)


def dt(f, **k):
    r = M.cliente().call(nome(), f, **k)
    r = r.get("returnValue", r) if isinstance(r, dict) else r
    return json.loads(r)


def ossos(ator):
    return dt("bone_world_positions", actor_label=ator, bones=OSSOS)["ossos"]


def dist(a, b):
    return math.dist(a, b)


def main(n_walk):
    ator = "TESTE_BONECO_0"
    TC.limpar()
    piso = M.cliente().call(SCENE, "add_to_scene_from_asset", asset_path="/Engine/BasicShapes/Cube.Cube", name="TESTE_PISO",
                            xform=TC.xform(TC.ZX, 400, -50, s=(6, 16, 1)))
    M.cliente().call(TC.ACTOR, "set_label", actor=piso if isinstance(piso, dict) else {"refPath": piso}, label="TESTE_PISO")
    TC.boneco(ator, TC.ZX, 0)
    for c in ("Start_Walking", "Walking", "Stop_Walking"):
        M.importar_clipe(c)
    M.aplicar_clipe(ator, "Walking", loop=True, manter_se_falhar=True, checar_movimento=False)  # correção de roll
    print("reload", dt("reload_toolset"))
    dt("set_pose_eval", actor_label=ator, on=True)
    o = ossos(ator)
    # frente = para onde os PÉS apontam (dedo − tornozelo, média dos dois); dedo − quadril pega o afastamento lateral
    fx = sum(o[f"{l}ToeBase"][0] - o[f"{l}Foot"][0] for l in ("Left", "Right"))
    fy = sum(o[f"{l}ToeBase"][1] - o[f"{l}Foot"][1] for l in ("Left", "Right"))
    frente = (0.0, 1.0) if abs(fy) >= abs(fx) else (1.0, 0.0)
    frente = (frente[0] * (1 if fx >= 0 else -1), frente[1] * (1 if fy >= 0 else -1))
    clipes = [f"/Game/_AnimLab/Mixamo/{c}_Anim.{c}_Anim" for c in ["Start_Walking"] + ["Walking"] * n_walk + ["Stop_Walking"]]
    s = dt("seq_chain_clips", actor_label=ator, clips_json=json.dumps(clipes), dir_x=frente[0], dir_y=frente[1], fps=FPS)
    print(json.dumps(s, ensure_ascii=False)[:600])
    res = {"frente": frente, "sequencia": s, "trocas": [], "video": None}
    seq = s["sequencia"]
    try:
        def em(q):
            dt("seq_eval_frame", sequence_path=seq, frame=q)
            M.cliente().call(SEQ, "set_playhead_frame", frame=q)  # field notes: playhead + force_evaluate
            M.cliente().call(SEQ, "force_evaluate")
            return ossos(ator)  # chamada separada: pose já reavaliada
        if os.environ.get("DIAG"):
            res["trajetoria"] = [(q, [round(v, 1) for v in em(q)["Hips"][:2]]) for q in range(80, 185, 6)]
        ini, fim = em(0), em(s["quadros"] - 1)
        res["avanco_medido_quadril_cm"] = round(dist(ini["Hips"][:2], fim["Hips"][:2]), 1)
        for f in s["faixas"][1:]:
            a, b = em(f["de"] - 1), em(f["de"])
            res["trocas"].append({"quadro": f["de"], "para": f["clipe"],
                                  "salto_quadril_cm": round(dist(a["Hips"], b["Hips"]), 1),
                                  "salto_dedos_cm": round(max(dist(a[k], b[k]) for k in ("LeftToeBase", "RightToeBase")), 1)})
        # vídeo: câmera isolada lateral, centrada no meio do caminho
        if os.environ.get("DIAG"):
            raise StopIteration  # diagnóstico: sem vídeo
        dt("capture_isolated_setup", actor_label=ator, yaw_deg=0.0 if frente[1] else 90.0, pitch_deg=8.0,
           distance_cm=650.0, width=640, height=360, also_show="", center_bone="")
        pngs = []
        for q in range(0, s["quadros"], 3):
            em(q)
            r = dt("capture_isolated_shot", directory=os.path.join(SAIDA, "quadros"), filename=f"q{len(pngs):04d}.png")  # numeração contínua para o ffmpeg
            if r.get("ok"):
                pngs.append(r["arquivo"])
        if pngs:
            import subprocess
            import imageio_ffmpeg
            mp4 = os.path.join(SAIDA, "andar_sequencer.mp4")
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-framerate", str(FPS // 3),
                            "-pattern_type", "sequence", "-start_number", "0", "-i",
                            os.path.join(SAIDA, "quadros", "q%04d.png"), "-vf", "fps=10", "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", mp4], check=True)
            res["video"] = {"arquivo": mp4, "quadros": len(pngs)}
    except StopIteration:
        pass
    finally:
        dt("capture_isolated_restore")
        res["fechar"] = dt("seq_close_delete", sequence_path=seq)
        TC.limpar()
    json.dump(res, open(os.path.join(SAIDA, "andar_sequencer.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: res.get(k) for k in ("trajetoria", "avanco_medido_quadril_cm", "trocas", "fechar")}, ensure_ascii=False))
    print("previsto (soma dos avanços):", s.get("avanco_total_cm"))


if __name__ == "__main__":
    trava.pegar(M.TRAVA, "claude-bloco2-seq", log=os.path.join(os.path.dirname(M.TRAVA), "trava.log"))
    M._pilha["n"] += 1
    try:
        main(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
    finally:
        M._pilha["n"] -= 1
        trava.soltar(M.TRAVA)
