"""v0.0.3 Bloco 2 — pedidos verticais V01 ("Marcos se levanta") e V02 ("... e vai até a porta") com movimentos
prontos (src/unreal_macros/blocos.py) no Sequencer (DirectorTools.seq_build). Cena de teste: piso, banco (caixa) e
porta (placa) TESTE_*; nada é salvo; sequências SEQ_TESTE_* apagadas no fim.
Uso: python tools/bloco2_v.py [V01|V02|V03|todos]"""
import json
import math
import os
import re
import subprocess
import sys

V003 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("UNREAL_MACROS_TRAVA", r"<repo>\work\unreal.trava")
sys.path.insert(0, os.path.join(V003, "src"))
os.chdir(os.path.join(V003, "src"))
import testes_contrato as TC  # noqa: E402
from unreal_macros import blocos as B, macros as M, trava  # noqa: E402
from unreal_macros.mcp_client import SCENE, SEQ  # noqa: E402

SAIDA = os.path.join(V003, "work", "bloco2")
FPS = 30
ATOR = "TESTE_BONECO_0"
OSSOS = "Hips,LeftFoot,RightFoot,LeftToeBase,RightToeBase"


def nome():
    return max(re.findall(r"[\w.]*DirectorTools\w*", M.cliente().list_toolsets()), key=len)


def dt(f, **k):
    r = M.cliente().call(nome(), f, **k)
    r = r.get("returnValue", r) if isinstance(r, dict) else r
    return json.loads(r)


def caixa(rotulo, x, y, z_base, sx, sy, sz):
    """Cubo básico (100 cm) com a base em z_base."""
    a = M.cliente().call(SCENE, "add_to_scene_from_asset", asset_path="/Engine/BasicShapes/Cube.Cube", name=rotulo,
                         xform=TC.xform(x, y, z_base + 50 * sz, s=(sx, sy, sz)))
    M.cliente().call(TC.ACTOR, "set_label", actor=a if isinstance(a, dict) else {"refPath": a}, label=rotulo)


def em(seq, q):
    dt("seq_eval_frame", sequence_path=seq, frame=q)
    M.cliente().call(SEQ, "set_playhead_frame", frame=q)  # field notes: playhead + force_evaluate
    M.cliente().call(SEQ, "force_evaluate")
    return dt("bone_world_positions", actor_label=ATOR, bones=OSSOS)["ossos"]


def registra(res, nome_t, esperado, observado, ok):
    res["testes"].append({"teste": nome_t, "esperado": esperado, "observado": observado, "ok": bool(ok)})
    print(("OK   " if ok else "FALHA") + f" {nome_t} | esperado: {esperado} | observado: {observado}")


def preparar():
    TC.limpar()
    caixa("TESTE_PISO", TC.ZX, 300, -100, 8, 14, 1)
    TC.boneco(ATOR, TC.ZX, 0)
    for c in B.CLIPES_NECESSARIOS["andar"] + B.CLIPES_NECESSARIOS["levantar"] + ("Open_Door_Outwards",):
        M.importar_clipe(c)
    M.aplicar_clipe(ATOR, "Walking", loop=True, manter_se_falhar=True, checar_movimento=False)  # correção de roll
    print("reload", dt("reload_toolset"))
    dt("set_pose_eval", actor_label=ATOR, on=True)
    o = dt("bone_world_positions", actor_label=ATOR, bones=OSSOS)["ossos"]
    fx = sum(o[f"{l}ToeBase"][0] - o[f"{l}Foot"][0] for l in ("Left", "Right"))
    fy = sum(o[f"{l}ToeBase"][1] - o[f"{l}Foot"][1] for l in ("Left", "Right"))
    frente = (0.0, math.copysign(1.0, fy)) if abs(fy) >= abs(fx) else (math.copysign(1.0, fx), 0.0)
    info = {c: dt("clip_info", animation_path=B.caminho(c)) for c in ("Start_Walking", "Walking", "Stop_Walking", "Sit_To_Stand", "Open_Door_Outwards")}
    return frente, info


def video(seq, quadros, nome_v, also, frente, yaw_extra=0.0):
    pasta = os.path.join(SAIDA, nome_v)
    os.makedirs(pasta, exist_ok=True)
    for f in os.listdir(pasta):
        os.remove(os.path.join(pasta, f))
    yaw = (180.0 if frente[1] else 270.0) + yaw_extra  # de lado, do lado iluminado (0/90 ficava contra a luz)
    n = 0
    for q in range(0, quadros, 2):
        em(seq, q)
        dt("capture_isolated_setup", actor_label=ATOR, yaw_deg=yaw, pitch_deg=6.0, distance_cm=420.0, width=640,
           height=360, also_show=also, center_bone="Hips")  # reposiciona a cada quadro: câmera que acompanha
        if dt("capture_isolated_shot", directory=pasta, filename=f"q{n:04d}.png").get("ok"):
            n += 1
    import imageio_ffmpeg
    mp4 = os.path.join(SAIDA, f"{nome_v}.mp4")
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-framerate", str(FPS // 2), "-i",
                    os.path.join(pasta, "q%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", mp4], check=True)
    return {"arquivo": mp4, "quadros": n}


def v01(frente, info, res):
    s = dt("seq_build", actor_label=ATOR, steps_json=json.dumps(B.levantar(info)["passos"]), dir_x=frente[0],
           dir_y=frente[1], fps=FPS)
    seq = s["sequencia"]
    res["sequencia"] = s
    try:
        o0 = em(seq, 0)
        hx, hy, hz = o0["Hips"]
        topo = hz - 10.0  # assento 10 cm abaixo da articulação do quadril sentado
        cx, cy = hx - frente[0] * 8, hy - frente[1] * 8
        caixa("TESTE_BANCO", cx, cy, 0.0, 0.45, 0.45, topo / 100.0)
        res["banco"] = {"centro": [round(cx, 1), round(cy, 1)], "topo_z": round(topo, 1)}
        registra(res, "começa sentado: quadril sobre o assento", "3 a 20 cm acima do topo", round(hz - topo, 1),
                 3 <= hz - topo <= 20)
        pen = []
        for q in range(0, s["quadros"], 6):
            o = em(seq, q)
            for pe in ("LeftFoot", "RightFoot"):
                x, y, z = o[pe]
                if abs(x - cx) < 22.5 and abs(y - cy) < 22.5 and z < topo:
                    pen.append((q, pe))
        registra(res, "pés nunca dentro do banco", "nenhum", pen, not pen)
        of = em(seq, s["quadros"] - 1)
        frente_do_banco = (of["Hips"][0] - cx) * frente[0] + (of["Hips"][1] - cy) * frente[1]
        dedos = max(of["LeftToeBase"][2], of["RightToeBase"][2])
        registra(res, "termina de pé", "quadril 88 a 105 cm", round(of["Hips"][2], 1), 88 <= of["Hips"][2] <= 105)
        registra(res, "pés no chão no fim", "dedos <= 8 cm", round(dedos, 1), dedos <= 8)
        registra(res, "termina à frente do banco", ">= 22 cm do centro", round(frente_do_banco, 1), frente_do_banco >= 22)
        res["video"] = video(seq, s["quadros"], "V01_levantar", "TESTE_BANCO,TESTE_PISO", frente)
    finally:
        dt("capture_isolated_restore")
        res["fechar"] = dt("seq_close_delete", sequence_path=seq)


def v02(frente, info, res):
    porta_dist = 450.0  # porta a 4,5 m do centro do banco, na frente dele
    o0 = None
    # o planejador calcula a caminhada: parar a 60 cm da porta
    lev = B.levantar(info)
    s0 = dt("seq_build", actor_label=ATOR, steps_json=json.dumps(lev["passos"]), dir_x=frente[0], dir_y=frente[1], fps=FPS)
    try:
        o0 = em(s0["sequencia"], 0)
    finally:
        dt("seq_close_delete", sequence_path=s0["sequencia"])
    hx, hy, hz = o0["Hips"]
    cx, cy, topo = hx - frente[0] * 8, hy - frente[1] * 8, hz - 10.0
    if not M.cliente().call(SCENE, "find_actors", name="TESTE_BANCO", tag="", collision_channels=["ObjectTypeQuery1"]):
        caixa("TESTE_BANCO", cx, cy, 0.0, 0.45, 0.45, topo / 100.0)
    px, py = cx + frente[0] * porta_dist, cy + frente[1] * porta_dist
    caixa("TESTE_PORTA", px, py, 0.0, 1.0 if frente[1] else 0.1, 0.1 if frente[1] else 1.0, 2.1)
    andar_cm = porta_dist - 60.0 - 8.0 - lev["avanco_cm"]
    receita = B.compor(lev, B.andar(andar_cm, info))
    res["receita"] = {"partes": receita["partes"], "andar_pedido_cm": round(andar_cm, 1), "avanco_previsto": receita["avanco_cm"]}
    s = dt("seq_build", actor_label=ATOR, steps_json=json.dumps(receita["passos"]), dir_x=frente[0], dir_y=frente[1], fps=FPS)
    seq = s["sequencia"]
    res["sequencia"] = s
    try:
        proj = lambda o: (o["Hips"][0] - px) * frente[0] + (o["Hips"][1] - py) * frente[1]  # < 0 = antes da porta
        maior = max(proj(em(seq, q)) for q in range(0, s["quadros"], 6))
        of = em(seq, s["quadros"] - 1)
        troca = s["faixas"][1]["de"]
        a, b = em(seq, troca - 1), em(seq, troca)
        salto = math.dist(a["Hips"], b["Hips"])
        registra(res, "nunca atravessa a porta", "projeção do quadril < 0", round(maior, 1), maior < 0)
        registra(res, "para perto da porta", "30 a 90 cm antes", round(-proj(of), 1), 30 <= -proj(of) <= 90)
        registra(res, "levantar → andar sem salto", "quadril <= 10 cm", round(salto, 1), salto <= 10)
        registra(res, "termina de pé", "quadril 88 a 105 cm", round(of["Hips"][2], 1), 88 <= of["Hips"][2] <= 105)
        res["video"] = video(seq, s["quadros"], "V02_levantar_ir_porta", "TESTE_BANCO,TESTE_PORTA,TESTE_PISO", frente)
    finally:
        dt("capture_isolated_restore")
        res["fechar"] = dt("seq_close_delete", sequence_path=seq)


CORPO = ("Hips,Spine2,Head,LeftArm,RightArm,LeftForeArm,RightForeArm,LeftHand,RightHand,LeftUpLeg,RightUpLeg,"
         "LeftLeg,RightLeg,LeftFoot,RightFoot")


def v03(frente, info, res):
    """V03 "Marcos vai até a porta e a abre": andar até a mão alcançar + Open_Door_Outwards; a folha é empurrada
    pelo corpo (blocos.angulos_porta), nunca animada à mão."""
    f = frente
    o = dt("bone_world_positions", actor_label=ATOR, bones=OSSOS)["ossos"]
    lado = (o["RightFoot"][0] - o["LeftFoot"][0], o["RightFoot"][1] - o["LeftFoot"][1])
    r = (-f[1], f[0]) if lado[0] * -f[1] + lado[1] * f[0] > 0 else (f[1], -f[0])  # direita do personagem
    porta_dist = 400.0
    larg = float(os.environ.get("LARGURA_PORTA", "120"))  # 100 cm: o braço do clipe bate na parede (06/10)
    meia = larg / 2
    dx, dy = o["Hips"][0] + f[0] * porta_dist, o["Hips"][1] + f[1] * porta_dist   # centro do vão
    lado_d = os.environ.get("DOBRADICA", "D") == "D"                             # D = direita do personagem
    sd = 1 if lado_d else -1
    hx, hy = dx + sd * r[0] * meia, dy + sd * r[1] * meia
    folha = (-sd * r[0], -sd * r[1])
    yaw0 = math.degrees(math.atan2(folha[1], folha[0]))
    for rot_, (cx, cy, sx) in (("TESTE_PORTA", (dx, dy, larg / 100)),
                               ("TESTE_PAREDE_E", (dx - r[0] * (meia + 75), dy - r[1] * (meia + 75), 1.5)),
                               ("TESTE_PAREDE_D", (dx + r[0] * (meia + 75), dy + r[1] * (meia + 75), 1.5))):
        a = M.cliente().call(SCENE, "add_to_scene_from_asset", asset_path="/Engine/BasicShapes/Cube.Cube", name=rot_,
                             xform=TC.xform(cx, cy, 105 if rot_ == "TESTE_PORTA" else 120, yaw=yaw0,
                                            s=(sx, 0.05 if rot_ == "TESTE_PORTA" else 0.12, 2.1 if rot_ == "TESTE_PORTA" else 2.4)))
        M.cliente().call(TC.ACTOR, "set_label", actor=a if isinstance(a, dict) else {"refPath": a}, label=rot_)
    # alcance: até onde a mão direita vai no começo do clipe de empurrar (espaço do corpo, frente = eixo 3)
    q_abrir = info["Open_Door_Outwards"]["quadros"]
    alcance = max(dt("bone_position_in_clip", animation_path=B.caminho("Open_Door_Outwards"), bone_name="RightHand",
                     frame=q)["xyz"][2] for q in range(0, min(40, q_abrir), 4))
    andar = B.andar(porta_dist - alcance, info)
    passos = andar["passos"] + [{"anim": B.caminho("Open_Door_Outwards")}]
    res["plano"] = {"alcance_mao_cm": round(alcance, 1), "andar": andar["avanco_cm"], "erro_andar_cm": andar["erro_cm"]}
    s = dt("seq_build", actor_label=ATOR, steps_json=json.dumps(passos), dir_x=f[0], dir_y=f[1], fps=FPS)
    seq = s["sequencia"]
    res["sequencia"] = s
    try:
        ini = s["faixas"][-2]["de"]  # do começo do "parar" ao fim: quando o corpo pode chegar na porta
        amostras = []
        for q in range(ini, s["quadros"], 2):
            dt("seq_eval_frame", sequence_path=seq, frame=q)
            M.cliente().call(SEQ, "set_playhead_frame", frame=q)
            M.cliente().call(SEQ, "force_evaluate")
            amostras.append((q, dt("bone_world_positions", actor_label=ATOR, bones=CORPO)["ossos"]))
        ang = B.angulos_porta(amostras, (hx, hy), f, folha, largura=larg)
        chaves = [[0, dx, dy, 105, yaw0], [max(ini - 1, 1), dx, dy, 105, yaw0]]
        for q, g in ang["angulos"]:
            (cx, cy), d = B.folha_em((hx, hy), folha, f, g, largura=larg)
            chaves.append([q, cx, cy, 105, math.degrees(math.atan2(d[1], d[0]))])
        res["porta"] = {"final_graus": ang["final_graus"], "primeiro_toque": ang["primeiro_toque"],
                        "chaves": dt("seq_key_transform", sequence_path=seq, actor_label="TESTE_PORTA",
                                     keys_json=json.dumps(chaves))}
        quadril = amostras[-1][1]["Hips"]
        s_fim = (quadril[0] - dx) * f[0] + (quadril[1] - dy) * f[1]
        lat_fim = (quadril[0] - dx) * r[0] + (quadril[1] - dy) * r[1]
        paredes = [(q, n, round(abs((p[0] - dx) * r[0] + (p[1] - dy) * r[1]) - meia, 1)) for q, os_ in amostras
                   for n, p in os_.items()
                   if abs((p[0] - dx) * f[0] + (p[1] - dy) * f[1]) < 8 and abs((p[0] - dx) * r[0] + (p[1] - dy) * r[1]) > meia + 5]
        res["porta"]["dobradica"] = "direita" if lado_d else "esquerda"
        res["porta"]["invasao_batente_max_cm"] = max([x[2] for x in paredes], default=0.0)
        toque = ang["primeiro_toque"] or {}
        registra(res, "a porta abre", ">= 60 graus", ang["final_graus"], ang["final_graus"] >= 60)
        registra(res, "começa a abrir pela mão (não pelo peito)", "mão ou antebraço", toque.get("osso"),
                 str(toque.get("osso", "")).endswith(("Hand", "ForeArm")))
        registra(res, "passa pelo vão", f"quadril >= 30 cm além, dentro do vão (|lat| < {meia - 5:.0f})",
                 (round(s_fim, 1), round(lat_fim, 1)), s_fim >= 30 and abs(lat_fim) < meia - 5)
        res["porta"]["largura_cm"] = larg
        registra(res, "não atravessa as paredes", "nenhum osso no plano fora do vão", paredes[:5], not paredes)
        res["video"] = video(seq, s["quadros"], "V03_abrir_porta", "TESTE_PORTA,TESTE_PAREDE_E,TESTE_PAREDE_D,TESTE_PISO", f,
                             yaw_extra=45.0)  # três-quartos por trás: a parede de perto não esconde a ação
    finally:
        dt("capture_isolated_restore")
        res["fechar"] = dt("seq_close_delete", sequence_path=seq)


if __name__ == "__main__":
    alvo = sys.argv[1] if len(sys.argv) > 1 else "todos"
    os.makedirs(SAIDA, exist_ok=True)
    trava.pegar(M.TRAVA, "claude-bloco2-v", log=os.path.join(os.path.dirname(M.TRAVA), "trava.log"))
    M._pilha["n"] += 1
    try:
        frente, info = preparar()
        for nome_v, fn in (("V01", v01), ("V02", v02), ("V03", v03)):
            if alvo in (nome_v, "todos"):
                res = {"pedido": nome_v, "frente": frente, "testes": []}
                try:
                    fn(frente, info, res)
                finally:
                    json.dump(res, open(os.path.join(SAIDA, f"{nome_v}.json"), "w", encoding="utf-8"),
                              ensure_ascii=False, indent=1)
                print(nome_v, f"{sum(t['ok'] for t in res['testes'])}/{len(res['testes'])}", res.get("video"))
    finally:
        try:
            TC.limpar()
        finally:
            M._pilha["n"] -= 1
            trava.soltar(M.TRAVA)
