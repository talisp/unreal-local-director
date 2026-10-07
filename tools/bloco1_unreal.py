"""v0.0.3 Bloco 1 — testes REAIS no Unreal do DirectorTools e das armadilhas das field notes do MCP 5.8.
Uso: python tools/bloco1_unreal.py <ping|campo|captura|ossos|todos>

Pré-requisitos: DirectorTools instalado (editor_python/LEIA.md), Hermes em PAUSA. O script toma a trava da PRODUÇÃO
(a mesma do Hermes) e a solta no fim. Só usa bonecos TESTE_* na zona x=10000; nada é salvo. Cada seção grava
work/bloco1/<secao>.json com esperado/observado."""
import datetime as dt
import json
import os
import re
import sys

V003 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("UNREAL_MACROS_TRAVA", r"<repo>\work\unreal.trava")
sys.path.insert(0, os.path.join(V003, "src"))
os.chdir(os.path.join(V003, "src"))
import testes_contrato as TC  # noqa: E402
from unreal_macros import macros as M, trava  # noqa: E402
from unreal_macros.mcp_client import APP, SCENE  # noqa: E402

SAIDA = os.path.join(V003, "work", "bloco1")
os.makedirs(SAIDA, exist_ok=True)
CLIPES = ("Talking_2", "Waving_2", "Hands_Forward_Gesture", "Walking")
linhas = []
_dt = {"nome": None}


def registra(nome, esperado, observado, ok, detalhe=None):
    linhas.append({"teste": nome, "esperado": esperado, "observado": observado, "ok": bool(ok), "detalhe": detalhe})
    print(("OK   " if ok else "FALHA") + f" {nome} | esperado: {esperado} | observado: {observado}")


def salvar(secao):
    json.dump({"secao": secao, "quando": dt.datetime.now().isoformat(timespec="seconds"),
               "versao_codigo": M.versao_codigo(), "resultados": linhas},
              open(os.path.join(SAIDA, f"{secao}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(f"{secao}: {sum(l['ok'] for l in linhas)}/{len(linhas)}")
    linhas.clear()


def dtools():
    """Nome completo do toolset, descoberto no catálogo (não chutado)."""
    if _dt["nome"] is None:
        achados = re.findall(r"[\w.]*DirectorTools\w*", M.cliente().list_toolsets())  # recarregar põe sufixo _0x...
        if not achados:
            raise SystemExit("DirectorTools não aparece em list_toolsets: instalação não carregou (ver Output Log)")
        _dt["nome"] = max(achados, key=len)
    return _dt["nome"]


PADROES = {"list_actors": {"class_name": "", "label_prefix": ""}, "bone_world_positions": {"bones": ""}}


def dt_call(ferramenta, **kw):
    kw = {**PADROES.get(ferramenta, {}), **kw}  # no MCP, argumento com padrão vira obrigatório (field notes, confirmado)
    r = M.cliente().call(dtools(), ferramenta, **kw)
    r = r.get("returnValue", r) if isinstance(r, dict) else r
    return json.loads(r) if isinstance(r, str) else r


# ---------- ping ----------
def s_ping():
    r = dt_call("ping")
    registra("DirectorTools responde com Python completo", "ok + motor 5.8", (r.get("ok"), r.get("motor")),
             r.get("ok") and str(r.get("motor", "")).startswith("5.8"), {"toolset": dtools(), **r})
    salvar("ping")


# ---------- armadilhas das field notes ----------
def s_campo():
    c = M.cliente()
    amplo = c.call(SCENE, "find_actors", name="", tag="", collision_channels=["ObjectTypeQuery1"]) or []
    completo = dt_call("list_actors")["total"]
    registra("find_actors corta em 20 sem avisar (field notes)", "len(find_actors) < total se total > 20",
             {"find_actors": len(amplo), "inventario_completo": completo}, True,
             {"corta": len(amplo) < completo, "exatamente_20": len(amplo) == 20})
    pcs = M._skeletal_actors()
    skel = dt_call("list_actors", class_name="SkeletalMeshActor")["total"]
    registra("_skeletal_actors do Director vê todos os personagens", skel, len(pcs), len(pcs) == skel,
             "se falhar: resolver_ator e limpar_estudio precisam do inventário completo")
    pedido = {"x": TC.ZX + 300.0, "y": -50.0, "z": 120.0}
    cap = c.call(APP, "CaptureViewport", captureTransform={"location": pedido, "rotation": {"pitch": 0, "yaw": 180, "roll": 0},
                                                              "scale": {"x": 1, "y": 1, "z": 1}},
                 annotations={"gridSpacing": 0, "maxLabelDistance": 0})
    rv = cap.get("returnValue", cap) if isinstance(cap, dict) else {}
    loc = rv.get("cameraLocation") if isinstance(rv, dict) else None
    registra("CaptureViewport usa a pose pedida (cameraLocation)", pedido, loc,
             bool(loc) and all(abs(float(loc[k]) - pedido[k]) < 1 for k in "xyz") if isinstance(loc, dict) else False,
             {"chaves_resposta": sorted(rv)[:12] if isinstance(rv, dict) else str(type(rv))})
    salvar("campo")


# ---------- captura isolada (VERA) ----------
def _silhueta(png):
    import numpy as np
    from PIL import Image
    a = np.asarray(Image.open(png).convert("RGB")).astype(int)
    fundo = a[0, 0]
    m = np.abs(a - fundo).sum(axis=2) > 30
    ys, xs = np.nonzero(m)
    if not len(ys):
        return {"pixels": 0}
    return {"pixels": int(m.sum()), "fracao": round(float(m.mean()), 4), "bbox_h": int(ys.max() - ys.min() + 1),
            "bbox_w": int(xs.max() - xs.min() + 1), "fundo_rgb": [int(v) for v in fundo]}


def s_captura():
    TC.limpar()
    TC.boneco("TESTE_BONECO_0", TC.ZX, 0)
    TC.boneco("TESTE_BONECO_1", TC.ZX + 80, 0)  # vizinho: NÃO pode aparecer na captura
    antes = sorted(a["rotulo"] for a in dt_call("list_actors")["atores"])
    fotos = {}
    try:
        for yaw in (0, 90):
            s = dt_call("capture_isolated_setup", actor_label="TESTE_BONECO_0", yaw_deg=yaw, pitch_deg=5.0,
                        distance_cm=0.0, width=512, height=512, also_show="", center_bone="")
            registra(f"setup da captura isolada (yaw {yaw})", True, s.get("ok"), s.get("ok"), s)
            r = dt_call("capture_isolated_shot", directory=SAIDA, filename=f"isolada_yaw{yaw}.png")
            registra(f"foto isolada gravada (yaw {yaw})", True, r.get("arquivo"), r.get("ok"), r)
            if r.get("ok"):
                fotos[yaw] = _silhueta(r["arquivo"])
    finally:
        rest = dt_call("capture_isolated_restore")
    registra("restauração da captura", True, rest.get("ok"), rest.get("ok"), rest)
    depois = sorted(a["rotulo"] for a in dt_call("list_actors")["atores"])
    registra("cena idêntica antes/depois (nenhum rig sobrando)", "sem diferença",
             sorted(set(antes) ^ set(depois)), antes == depois)
    for yaw, s in fotos.items():
        # fundo uniforme (céu desligado) e um boneco só: silhueta pequena, inteira dentro da imagem
        registra(f"silhueta isolada (yaw {yaw})", "fundo uniforme, 0 < fração < 0,25, bbox dentro da imagem", s,
                 0 < s.get("fracao", 1) < 0.25 and s.get("bbox_h", 512) < 500, s)
    TC.limpar()
    salvar("captura")


# ---------- ossos x silhueta (estúdio v2) ----------
def s_ossos():
    from unreal_macros import workflows as W
    TC.limpar()
    piso = M.cliente().call(SCENE, "add_to_scene_from_asset", asset_path="/Engine/BasicShapes/Cube.Cube", name="TESTE_PISO",
                            xform=TC.xform(TC.ZX + 225, 0, -50, s=(12, 12, 1)))  # sem piso o portão pes_no_chao reprova
    M.cliente().call(TC.ACTOR, "set_label", actor=piso if isinstance(piso, dict) else {"refPath": piso}, label="TESTE_PISO")
    for i, clipe in enumerate(CLIPES):
        ator = f"TESTE_BONECO_{i}"
        TC.boneco(ator, TC.ZX + i * 150, 0)
        M.importar_clipe(clipe)
        rel = M.aplicar_clipe(ator, clipe, loop=True, manter_se_falhar=True, checar_movimento=False)
        a = M.resolver_ator(ator)
        gs = {g["nome"]: g for g in W._gate_deriva(a, 15.0)}
        dt_call("set_pose_eval", actor_label=ator, on=True)
        todos = dt_call("bone_world_positions", actor_label=ator)  # chamada SEPARADA da que liga a avaliação
        ossos = {n: p for n, p in todos.get("ossos", {}).items() if re.search(r"foot|toe|hips", n, re.I)}
        pes_z = [p[2] for n, p in ossos.items() if re.search(r"foot|toe", n, re.I)]
        registra(f"ossos lidos: {clipe}", "pés e quadril", sorted(ossos)[:8], bool(pes_z),
                 {"ossos": ossos, "pes_z_min": min(pes_z) if pes_z else None,
                  "silhueta": {k: (gs.get(k, {}).get("resultado"), gs.get(k, {}).get("valor")) for k in gs},
                  "aplicar_ok": rel["ok"], "aplicar_bloqueio": rel["bloqueio"]})
        M._restaurar(a, rel["medidas"]["antes"]["props"])
    dt_call("capture_isolated_restore")  # devolve a opção de tick de todos
    TC.limpar()
    salvar("ossos")


SECOES = {"ping": s_ping, "campo": s_campo, "captura": s_captura, "ossos": s_ossos}

if __name__ == "__main__":
    alvo = sys.argv[1] if len(sys.argv) > 1 else "ping"
    trava.pegar(M.TRAVA, "claude-bloco1-v003", log=os.path.join(os.path.dirname(M.TRAVA), "trava.log"))
    M._pilha["n"] += 1  # o script é o operador externo: as macros rodam "por dentro" e não soltam a trava no meio
    try:
        for nome in (SECOES if alvo == "todos" else [alvo]):
            SECOES[nome]()
    finally:
        M._pilha["n"] -= 1
        trava.soltar(M.TRAVA)
