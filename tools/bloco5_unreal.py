"""Bloco 5 — testes REAIS no Unreal da v0.0.2 (uma seção por vez: python bloco5_unreal.py <secao>).

Regras: Hermes parado; trava da produção segurada pelo Claude; só bonecos TESTE_* (v0.0.2 em x=10000, sandbox de
teste em x=20000); para no primeiro ESTADO PARCIAL. Cada seção grava work/bloco5/<secao>.json com esperado/observado.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time

V002 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(V002, "src")
SB_TESTE = r"<sandbox>-v002"
PROD = r"<repo>"
sys.path.insert(0, SRC)
os.chdir(SRC)
import testes_contrato as TC  # noqa: E402
from unreal_macros import catalogo, diario, macros as M  # noqa: E402

SAIDA = os.path.join(V002, "work", "bloco5")
os.makedirs(SAIDA, exist_ok=True)
linhas = []


def registra(nome, esperado, observado, ok, detalhe=None):
    linhas.append({"teste": nome, "esperado": esperado, "observado": observado, "ok": bool(ok), "detalhe": detalhe})
    print(("OK   " if ok else "FALHA") + f" {nome} | esperado: {esperado} | observado: {observado}")


def checar_parcial(rel):
    if "ESTADO PARCIAL" in json.dumps(rel, default=str) or (rel.get("medidas", {}).get("restaurado") is False):
        salvar("ABORTADO")
        raise SystemExit("ESTADO PARCIAL real: testes no Unreal interrompidos (regra do bloco 5)")


def salvar(secao):
    json.dump({"secao": secao, "quando": dt.datetime.now().isoformat(timespec="seconds"),
               "versao_codigo": M.versao_codigo(), "resultados": linhas},
              open(os.path.join(SAIDA, f"{secao}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(f"{secao}: {sum(l['ok'] for l in linhas)}/{len(linhas)}")


def cena_teste():
    TC.limpar()
    piso = TC.c.call(TC.SCENE, "add_to_scene_from_asset", asset_path="/Engine/BasicShapes/Cube.Cube", name="TESTE_PISO",
                     xform=TC.xform(TC.ZX, 0, -50, s=(12, 12, 1)))
    TC.c.call(TC.ACTOR, "set_label", actor=piso if isinstance(piso, dict) else {"refPath": piso}, label="TESTE_PISO")
    for i in range(4):
        TC.boneco(f"TESTE_BONECO_{i}", TC.ZX + i * 150, 0)


# ---------- 0: estado inicial ----------
def s0_estado():
    from unreal_macros.mcp_client import APP, Client
    c = Client(timeout=20)
    pie = c.call(APP, "IsPIERunning")
    r = M.inspecionar_cena(filtro="")
    labels = [p["rotulo"] for p in r["medidas"].get("personagens", [])]
    prod = subprocess.run(["sha256sum", "-c", "--quiet", "work/hashes_producao_0610b.txt"], cwd=PROD, capture_output=True, text=True)
    registra("Unreal sem Play", False, pie, pie is False)
    registra("sem bonecos TESTE_ sobrando", [], [l for l in labels if l.startswith("TESTE_")], not [l for l in labels if l.startswith("TESTE_")])
    registra("produção intacta (hashes)", 0, prod.returncode, prod.returncode == 0)
    registra("relatório traz versao_codigo", M.versao_codigo(), r["ambiente"].get("versao_codigo"), r["ambiente"].get("versao_codigo") == M.versao_codigo())
    linhas.append({"teste": "personagens do LAB (contagem)", "observado": len(labels), "ok": True})
    salvar("s0_estado")


# ---------- 2: smoke ----------
def s2_smoke():
    cena_teste()
    r = M.inspecionar_cena(filtro="TESTE")
    registra("inspecionar_cena acha os bonecos de teste", 4, len(r["medidas"]["personagens"]), len(r["medidas"]["personagens"]) == 4)
    M.importar_clipe("Head_Nod_Yes")
    pos = M.aplicar_clipe("TESTE_BONECO_0", "Head_Nod_Yes", loop=True)
    checar_parcial(pos)
    registra("positivo conhecido (Head_Nod_Yes)", True, pos["ok"], pos["ok"], pos["bloqueio"])
    M.importar_clipe("Rifle_Crouch_Walk_To_Kneel")
    neg = M.aplicar_clipe("TESTE_BONECO_1", "Rifle_Crouch_Walk_To_Kneel", loop=True)
    checar_parcial(neg)
    falhos = sorted(g["nome"] for g in neg["medidas"].get("gates", []) if g["resultado"] != "PASS")
    registra("controle negativo (termina ajoelhado) reprova pelo gate de pose", "silhueta_de_pe ou pose_em_todo_clipe",
             falhos, neg["ok"] is False and bool({"silhueta_de_pe", "pose_em_todo_clipe"} & set(falhos)))
    registra("reprovação restaurou e conferiu", True, neg["medidas"].get("restaurado"), neg["medidas"].get("restaurado") is True)
    med = M.medir_personagem("TESTE_BONECO_0", com_vizinhos=False)
    s = med["medidas"].get("silhueta", {})
    registra("medição de pé (Head_Nod aplicado)", "160-210 cm, |gap|<=4", (s.get("altura_cm"), s.get("gap_local_cm")), med["ok"])
    for rel, nome in ((pos, "aplicar"), (neg, "aplicar(neg)"), (med, "medir")):
        disco = diario.carregar_relatorio(rel["id"])
        registra(f"relatório {nome} persistido com versão", rel["id"], disco.get("id"),
                 disco.get("id") == rel["id"] and disco["ambiente"].get("versao_codigo") == M.versao_codigo())
    import tempfile
    tmp = tempfile.mkdtemp()
    lin = diario.registrar(diario.carregar_relatorio(pos["id"]), tmp, macro="aplicar_clipe", fonte="relatorio_id")["linha"]
    registra("registrar_tentativa pelo id: números iguais ao relatório", (pos["segundos"], pos["chamadas"]),
             (lin["segundos"], lin["chamadas"]), (lin["segundos"], lin["chamadas"]) == (pos["segundos"], pos["chamadas"]))
    salvar("s2_smoke")


# ---------- 3: bloco 1 no Unreal ----------
def s3_deriva():
    from unreal_macros import workflows as W
    cena_teste()
    casos = (("Talking_2", "PASS"), ("Waving_2", "PASS"), ("Hands_Forward_Gesture", "PASS"), ("Walking", "FAIL"))
    for i, (clipe, esperado) in enumerate(casos):
        M.importar_clipe(clipe)
        ator = f"TESTE_BONECO_{i}"
        rel = M.aplicar_clipe(ator, clipe, loop=True, manter_se_falhar=True, checar_movimento=False)
        checar_parcial(rel)
        a = M.resolver_ator(ator)
        gs = {g["nome"]: g for g in W._gate_deriva(a, 15.0)}
        d = gs.get("deriva_xy", {})
        registra(f"deriva pelas pernas: {clipe}", f"deriva_xy {esperado}", (d.get("resultado"), d.get("valor")),
                 d.get("resultado") == esperado, {"pes_plantados": gs.get("pes_plantados", {}).get("valor"),
                                                   "aplicar_ok": rel["ok"], "aplicar_bloqueio": rel["bloqueio"]})
        ok_rest = M._restaurar(a, rel["medidas"]["antes"]["props"])
        registra(f"restauração depois de {clipe}", True, ok_rest, ok_rest)
        if not ok_rest:
            salvar("s3_deriva")
            raise SystemExit("restauração não conferiu: parando (regra do bloco 5)")
    salvar("s3_deriva")


def s3_captura():
    cena_teste()
    M.importar_clipe("Head_Nod_Yes")
    M.aplicar_clipe("TESTE_BONECO_0", "Head_Nod_Yes", loop=True)
    res = {}
    for chave, env in (("OFF", {}), ("ON", {"ULD_CAPTURA_ESTAVEL": "1"})):
        cod = ("import sys, json; sys.path.insert(0, %r); from unreal_macros import macros as M; "
               "r = M.medir_personagem('TESTE_BONECO_0', com_vizinhos=False); s = r['medidas'].get('silhueta', {}); "
               "print('RES ' + json.dumps({'ok': r['ok'], 'chamadas': r['chamadas'], 'segundos': r['segundos'], "
               "'gap': s.get('gap_local_cm'), 'estab': 'estabilidade' in s, 'obs': s.get('observacoes_gap')}))") % SRC
        out = subprocess.run([sys.executable, "-X", "utf8", "-c", cod], capture_output=True, text=True, encoding="utf-8",
                             env=dict(os.environ, **env), cwd=SRC)
        res[chave] = json.loads([l for l in out.stdout.splitlines() if l.startswith("RES ")][0][4:])
    registra("captura OFF: caminho antigo (sem 'estabilidade')", False, res["OFF"]["estab"], res["OFF"]["estab"] is False, res["OFF"])
    registra("captura ON: caminho novo declarado no relatório", True, res["ON"]["estab"], res["ON"]["estab"] is True, res["ON"])
    linhas.append({"teste": "custo OFF x ON (informativo)", "observado": {k: (v["chamadas"], v["segundos"], v["gap"]) for k, v in res.items()}, "ok": True})
    salvar("s3_captura")


if __name__ == "__main__":
    {"s0": s0_estado, "s2": s2_smoke, "s3d": s3_deriva, "s3c": s3_captura}[sys.argv[1]]()
