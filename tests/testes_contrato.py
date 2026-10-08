"""Testes de contrato das macros contra o Unreal vivo, numa zona de testes isolada (x = 10000).

Regras: só cria atores TESTE_*; apaga todos no fim; nunca salva o level; não toca em nenhum outro ator.
Resultado em work/testes_contrato.json. Uso: python testes_contrato.py
"""
import datetime as dt
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from unreal_macros import catalogo, macros as M  # noqa: E402
from unreal_macros.mcp_client import ACTOR, OBJECT, SCENE  # noqa: E402

ZX = 10000.0
c = M.cliente()
resultados = []


def registra(nome, esperado, rel, passou):
    resultados.append({"teste": nome, "esperado": esperado, "passou": bool(passou), "ok_macro": rel.get("ok"),
                       "bloqueio": rel.get("bloqueio"), "gates": rel.get("medidas", {}).get("gates"),
                       "ajuste_z": rel.get("medidas", {}).get("ajuste_z_cm"), "chamadas": rel.get("chamadas"),
                       "segundos": rel.get("segundos")})
    print(("OK  " if passou else "FALHA"), nome, "| ok_macro:", rel.get("ok"), "|", rel.get("bloqueio"), flush=True)


def xform(x, y, z, yaw=0.0, s=(1, 1, 1)):
    return {"location": {"x": x, "y": y, "z": z}, "rotation": {"pitch": 0, "yaw": yaw, "roll": 0},
            "scale": {"x": s[0], "y": s[1], "z": s[2]}}


def teste_actors():
    out = []
    for a in c.call(SCENE, "find_actors", name="TESTE_", tag="", collision_channels=["ObjectTypeQuery1"]) or []:
        try:
            lab = c.call(ACTOR, "get_label", actor=a)
        except Exception:
            lab = ""
        if str(lab).startswith("TESTE_"):
            out.append(a)
    return out


def limpar():
    for a in teste_actors():
        c.call(SCENE, "remove_from_scene", actor=a)
    M._estudio["piso"] = None
    M._cache_rotulos["t"] = 0


def boneco(nome, x, y, yaw=0.0):
    a = c.call(SCENE, "add_to_scene_from_class", actor_type={"refPath": "/Script/Engine.SkeletalMeshActor"},
               name=nome, xform=xform(x, y, 0, yaw))
    a = a if isinstance(a, dict) else {"refPath": a}
    c.call(ACTOR, "set_label", actor=a, label=nome)
    c.call(OBJECT, "set_properties", instance={"refPath": a["refPath"] + M.COMP},
           values=json.dumps({"skeletalMeshAsset": {"refPath": M.MALHA_YBOT}}))
    return a


def main():
    limpar()
    piso = c.call(SCENE, "add_to_scene_from_asset", asset_path="/Engine/BasicShapes/Cube.Cube", name="TESTE_PISO",
                  xform=xform(ZX, 0, -50, s=(12, 12, 1)))
    piso = piso if isinstance(piso, dict) else {"refPath": piso}
    c.call(ACTOR, "set_label", actor=piso, label="TESTE_PISO")
    a = boneco("TESTE_BONECO_A", ZX, 0)
    time.sleep(0.5)

    r = M.inspecionar_cena(filtro="TESTE")
    registra("inspecionar_cena encontra o boneco de teste", "PASS", r,
             r["ok"] and any(p["rotulo"] == "TESTE_BONECO_A" for p in r["medidas"].get("personagens", [])))

    r = catalogo.buscar_clipe("head nod yes", n=3)
    registra("buscar_clipe acha Head_Nod_Yes", "PASS", r, r["ok"] and r["medidas"]["clipes"][0]["nome"] == "Head_Nod_Yes")

    for i, clipe in enumerate(("Head_Nod_Yes", "Thoughtful_Head_Nod", "Arm_Gesture")):
        ri = M.importar_clipe(clipe)
        registra(f"importar_clipe {clipe}", "PASS", ri, ri["ok"])
        ra = M.aplicar_clipe("TESTE_BONECO_A", clipe, loop=True)
        registra(f"aplicar_clipe {clipe} (de pé pela silhueta no estúdio, pés no piso, ator parado)", "PASS", ra, ra["ok"])

    # Controle negativo 1: clipe da biblioteca SEM o roll 90 (o erro antigo) deve reprovar a silhueta de pé.
    cn = boneco("TESTE_BONECO_C", ZX - 300, 0)
    M.aplicar_clipe("TESTE_BONECO_C", "Head_Nod_Yes", loop=False, corrigir_altura=False)
    c.call(OBJECT, "set_properties", instance={"refPath": cn["refPath"] + M.COMP},
           values=json.dumps({"relativeRotation": {"pitch": 0, "yaw": 0, "roll": 0}}))
    time.sleep(0.5)
    rn = M.medir_personagem("TESTE_BONECO_C", com_vizinhos=False)
    registra("CONTROLE: clipe da biblioteca sem roll 90 reprova silhueta_de_pe", "FAIL", rn, rn["ok"] is False)

    # Controle negativo 2: boneco B a 30 cm do A -> distância entre bases tem de reprovar.
    b = boneco("TESTE_BONECO_B", ZX + 30, 0)
    M.aplicar_clipe("TESTE_BONECO_B", "Head_Nod_Yes", loop=False)
    rm = M.medir_personagem("TESTE_BONECO_A")
    dv = [gg for gg in rm["medidas"].get("gates", []) if gg["nome"] == "distancia_vizinhos"]
    registra("CONTROLE: medir_personagem detecta vizinho colado", "FAIL", rm, bool(dv) and dv[0]["resultado"] == "FAIL")
    c.call(ACTOR, "set_actor_transform", actor=b, xform=xform(ZX + 400, 0, 0))
    c.call(ACTOR, "set_actor_transform", actor=cn, xform=xform(ZX - 600, 0, 0))
    time.sleep(0.3)
    rm = M.medir_personagem("TESTE_BONECO_A")
    registra("medir_personagem: de pé, pés no chão, sem vizinho colado", "PASS", rm, rm["ok"])
    # Estúdio v2 (06/10): a silhueta tem de sair COMPLETA (corpo inteiro ~4000-7000 cm2), com resolução suficiente.
    sv = rm["medidas"].get("silhueta", {})
    registra("estúdio: silhueta completa (área >= 4000 cm2, >= 1.0 px/cm)", "PASS", rm,
             (sv.get("area_cm2") or 0) >= 4000 and (sv.get("px_por_cm") or 0) >= 1.0)

    # Controles negativos dos gates de 06/10 (bancada do Hermes): cada um tem de REPROVAR e restaurar.
    # Astra: conferir o MOTIVO (gate ou aviso esperado), não só "reprovou".
    for clipe, porque, motivos in (("Walking", "anda no lugar", {"pes_no_chao", "pes_plantados", "pose_em_todo_clipe"}),
                                   ("Falling_Idle", "pose sem chão (ajuste > 10 cm)", {"ajuste permitido"}),
                                   ("Rifle_Crouch_Walk_To_Kneel", "termina ajoelhado", {"silhueta_de_pe", "pose_em_todo_clipe"})):
        M.importar_clipe(clipe)
        rx = M.aplicar_clipe("TESTE_BONECO_A", clipe, loop=True)
        reprovados = {gg["nome"] for gg in rx["medidas"].get("gates", []) if gg["resultado"] != "PASS"}
        texto = " ".join(rx["avisos"]) + " " + " ".join(reprovados)
        registra(f"CONTROLE: {clipe} reprova: {porque} (reprovou: {sorted(reprovados)})", "FAIL", rx,
                 rx["ok"] is False and rx["medidas"].get("restaurado") is True and any(m in texto for m in motivos))

    rc = M.capturar_evidencia("TESTE_BONECO_A", vista="frontal", nome="TESTE contrato")
    registra("capturar_evidencia gera PNG enquadrado", "PASS", rc, rc["ok"] and rc["evidencias"] and os.path.exists(rc["evidencias"][0]))

    re_ = M.chamada_avancada("editor_toolset.toolsets.asset.AssetTools", "save_assets",
                             {"asset_paths": ["/Game/Maps/SalaAudiencia_Integrada"]}, motivo="teste de recusa da política")
    registra("CONTROLE: escotilha recusa salvar a sala", "FAIL", re_, re_["ok"] is False)

    # A02: gate impossível (tolerância negativa) -> a macro tem de restaurar o estado anterior e conferir.
    antes = M._props(M.resolver_ator("TESTE_BONECO_A"))
    rf = M.aplicar_clipe("TESTE_BONECO_A", "Thoughtful_Head_Nod", loop=False, tolerancia_cm=-1)
    depois = M._props(M.resolver_ator("TESTE_BONECO_A"))
    igual = M._ref(antes["animationData"].get("animToPlay")) == M._ref(depois["animationData"].get("animToPlay")) and         all(M._igual(antes[k], depois[k]) for k in ("relativeLocation", "relativeRotation"))
    registra("CONTROLE: reprovação restaura o estado anterior (A02)", "FAIL", rf,
             rf["ok"] is False and rf["medidas"].get("restaurado") is True and igual)
    # A01: escotilha recusa escrita/script.
    re2 = M.chamada_avancada("editor_toolset.toolsets.programmatic.ProgrammaticToolset", "execute_tool_script",
                             {"script": "def run(): return {}"}, motivo="teste de recusa de script pela escotilha")
    registra("CONTROLE: escotilha recusa execute_tool_script (A01)", "FAIL", re2, re2["ok"] is False and "LEITURA" in (re2["bloqueio"] or ""))
    # A08: clipe de família desconhecida é recusado.
    rd = M.aplicar_clipe("TESTE_BONECO_A", "/Game/Characters/SK_YBot.SK_YBot", loop=False)
    registra("CONTROLE: família de clipe desconhecida é recusada (A08)", "FAIL", rd, rd["ok"] is False and "família" in (rd["bloqueio"] or ""))
    # A11: cartão sem 'clipe' em aplicar_clipe é inválido.
    from unreal_macros import cartao as K
    rk = K.validar_cartao({"objetivo": "cartão incompleto", "passos": [{"id": "x", "acao": "aplicar_clipe", "ator": "TESTE_BONECO_A"}]})
    registra("CONTROLE: cartão sem campo obrigatório é recusado (A11)", "FAIL", rk, rk["ok"] is False)

    limpar()
    sobrou = teste_actors()
    resultados.append({"teste": "limpeza: nenhum TESTE_* sobrou", "passou": not sobrou})
    print("limpeza:", "ok" if not sobrou else sobrou)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        resultados.append({"teste": "EXCEÇÃO", "passou": False, "erro": traceback.format_exc()[-1500:]})
        try:
            limpar()
        except Exception:
            pass
    out = {"quando": dt.datetime.now().isoformat(timespec="minutes"), "resultados": resultados,
           "passaram": sum(r["passou"] for r in resultados), "total": len(resultados), "log_chamadas": len(c.log)}
    json.dump(out, open(os.path.join(os.path.dirname(__file__), "..", "work", "testes_contrato.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"{out['passaram']}/{out['total']} testes ok, {out['log_chamadas']} chamadas ao Unreal")
    sys.exit(0 if resultados and all(r["passou"] for r in resultados) else 1)
