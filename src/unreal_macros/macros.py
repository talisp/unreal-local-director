"""Macros do Hermes: uma tarefa por função, com leitura de volta e medida embutidas.

Toda macro devolve o relatório padrão da política:
{macro, ok, medidas, evidencias, avisos, bloqueio, contexto, chamadas, segundos}.
"""
import base64
import datetime as dt
import functools
import json
import os
import re
import time

from . import gates
from .mcp_client import ACTOR, APP, ASSET, OBJECT, SCENE, SKMESH, Client, UnrealError

RAIZ_WORK = os.path.join(os.path.dirname(__file__), "..", "..", "work")
CENAS = os.environ.get("ULD_EVIDENCE_DIR", os.path.join(RAIZ_WORK, "evidence"))
BIBLIOTECA = os.environ.get("ULD_CLIP_LIBRARY", os.path.join(RAIZ_WORK, "clip_library"))
PASTA_CLIPES = "/Game/_AnimLab/Mixamo"
ESQUELETO = "/Game/Characters/SK_YBot_Skeleton.SK_YBot_Skeleton"
MALHA_YBOT = "/Game/Characters/SK_YBot.SK_YBot"
ESCOTILHA_LEITURA = ("get_", "find_", "list_", "describe", "exists", "is_dirty", "is_checked_out", "can_edit",
                     "trace_world", "search_subclasses", "Get", "WorldPosToScreenCoords", "ScreenCoordsToWorld", "IsPIERunning")
PROIBIDO_SALVAR = ("/Game/Maps/SalaAudiencia_Integrada", "/Game/Characters/SK_YBot", "/Game/Characters/SK_YBot_Skeleton")
COMP = ".SkeletalMeshComponent0"
CALIB_PES_CM = 9.0  # deslocamento sistemático dos pés na silhueta (câmera 170 cm, 4,2 m, olhando 90 cm)
PROPS_ANIM = ["animationMode", "animationData", "bUseRefPoseOnInitAnim", "relativeLocation", "relativeRotation", "skeletalMeshAsset"]

_cliente = None
RUN = f"{os.getpid()}"  # identifica os temporários desta execução (estúdio)
TRAVA = os.environ.get("UNREAL_MACROS_TRAVA") or os.path.join(RAIZ_WORK, "unreal.trava")  # o sandbox usa a MESMA trava
PRAZO_MACRO_S = 1500
_pilha = {"n": 0, "cam": None, "trava": False}


def _pegar_trava(nome: str):
    """Trava de um operador por vez no Unreal (política, regra 9). Trava velha (> 40 min) é tomada."""
    os.makedirs(RAIZ_WORK, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(TRAVA, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, json.dumps({"pid": os.getpid(), "macro": nome, "desde": time.time()}).encode())
            os.close(fd)
            return
        except FileExistsError:
            try:
                info = json.load(open(TRAVA, encoding="utf-8"))
            except Exception:
                info = {"desde": 0}
            if time.time() - info.get("desde", 0) > 2400 or info.get("pid") == os.getpid():
                os.remove(TRAVA)
                continue
            raise RuntimeError(f"Unreal ocupado por outro operador ({info}); espere ou confira com o operador")
    raise RuntimeError("não consegui a trava do Unreal")


def _soltar_trava():
    try:
        if json.load(open(TRAVA, encoding="utf-8")).get("pid") == os.getpid():
            os.remove(TRAVA)
    except Exception:
        pass


def cliente() -> Client:
    global _cliente
    if _cliente is None:
        _cliente = Client().connect()
    return _cliente


def macro(fn):
    """Envolve a função no relatório padrão (tempo, nº de chamadas, erro vira bloqueio)."""
    @functools.wraps(fn)
    def wrapper(*args, contexto=None, **kwargs):
        c = cliente()
        n0, t0 = len(c.log), time.time()
        rel = {"macro": fn.__name__, "ok": False, "medidas": {}, "evidencias": [], "avisos": [],
               "bloqueio": None, "contexto": contexto or {}}
        externo = _pilha["n"] == 0
        _pilha["n"] += 1
        try:
            if externo and getattr(fn, "_usa_unreal", True):
                _pegar_trava(fn.__name__)
                _pilha["trava"] = True
                c.prazo = time.time() + PRAZO_MACRO_S
                if c.call(APP, "IsPIERunning"):  # com Play ativo o editor recusa criar/apagar atores (06/10)
                    raise RuntimeError("o Unreal está em modo Play (PIE): peça ao operador para parar o Play; nada foi feito")
                try:
                    _pilha["cam"] = c.call(APP, "GetCameraTransform")
                except Exception:
                    _pilha["cam"] = None
            fn(rel, *args, **kwargs)
            if rel["bloqueio"] is None and "gates" in rel["medidas"]:
                rel["ok"] = all(g["resultado"] == "PASS" for g in rel["medidas"]["gates"])
                if not rel["ok"]:
                    rel["bloqueio"] = "gate reprovado: " + ", ".join(g["nome"] for g in rel["medidas"]["gates"] if g["resultado"] != "PASS")
            elif rel["bloqueio"] is None:
                rel["ok"] = True
        except Exception as e:  # qualquer falha vira bloqueio no relatório, nunca exceção para o Hermes
            rel["ok"] = False
            rel["bloqueio"] = f"{type(e).__name__}: {str(e)[:500]}"
        finally:
            _pilha["n"] -= 1
            if externo:
                c.prazo = None
                if _pilha["cam"]:  # devolve a câmera do viewport ao lugar (A10)
                    try:
                        cam = _pilha["cam"]
                        c.call(APP, "SetCameraTransform", transform={"location": cam["location"], "rotation": cam["rotation"]})
                    except Exception:
                        rel["avisos"].append("não consegui devolver a câmera ao lugar")
                    _pilha["cam"] = None
                if _pilha["trava"]:
                    _soltar_trava()
                    _pilha["trava"] = False
        rel["chamadas"] = len(c.log) - n0
        rel["segundos"] = round(time.time() - t0, 1)
        return rel
    return wrapper


# ---------- auxiliares (camada atômica, nunca expostas ao Hermes) ----------

def _nivel() -> str:
    lvl = cliente().call(SCENE, "get_current_level")
    lvl = lvl if isinstance(lvl, str) else lvl.get("refPath", str(lvl))
    base = lvl.split(".")[0]
    return f"{base}.{base.split('/')[-1]}:PersistentLevel."


def _skeletal_actors() -> list:
    return cliente().call(SCENE, "find_actors", name="", tag="", collision_channels=["ObjectTypeQuery1"],
                          actor_type={"refPath": "/Script/Engine.SkeletalMeshActor"}) or []


_cache_rotulos = {"t": 0.0, "mapa": {}}


def _mapa_rotulos(forcar: bool = False) -> dict:
    """rótulo -> ator, com cache de 60 s (consultar o rótulo de todos os atores custa ~30 chamadas)."""
    if forcar or time.time() - _cache_rotulos["t"] > 60:
        _cache_rotulos["mapa"] = {_label(a): a for a in _skeletal_actors()}
        _cache_rotulos["t"] = time.time()
    return _cache_rotulos["mapa"]


def resolver_ator(nome: str) -> dict:
    """Aceita rótulo (PC_18_Mezz01), nome interno (SkeletalMeshActor_18) ou refPath."""
    if nome.startswith("/Game/"):
        return {"refPath": nome}
    if nome.startswith("SkeletalMeshActor") or nome.startswith("TESTE_"):
        for a in _skeletal_actors():
            if a["refPath"].endswith("." + nome):
                return a
    for forcar in (False, True):
        a = _mapa_rotulos(forcar).get(nome)
        if a:
            return a
    raise ValueError(f"ator não encontrado: {nome}")


def _ref(v) -> str:
    """Referência de asset que pode vir como {'refPath': ...}, texto ou None."""
    if isinstance(v, dict):
        return v.get("refPath") or ""
    return "" if v in (None, "None") else str(v)


def _label(a: dict) -> str:
    try:
        return cliente().call(ACTOR, "get_label", actor=a)
    except UnrealError:
        return a["refPath"].split(".")[-1]


def _props(a: dict, props=PROPS_ANIM) -> dict:
    p = cliente().call(OBJECT, "get_properties", instance={"refPath": a["refPath"] + COMP}, properties=props)
    return json.loads(p) if isinstance(p, str) else p


def _set(a: dict, valores: dict):
    """set_properties exige `values` como TEXTO JSON (FALHA-11); lê de volta e confere."""
    ok = cliente().call(OBJECT, "set_properties", instance={"refPath": a["refPath"] + COMP}, values=json.dumps(valores))
    if ok is False:
        raise UnrealError(f"set_properties recusou {list(valores)}")
    lido = _props(a, list(valores))
    for k, v in valores.items():
        if not _igual(v, lido.get(k)):
            raise UnrealError(f"leitura de volta de {k}: esperado {v}, lido {lido.get(k)}")
    return lido


def _igual(esperado, lido, tol: float = 0.05) -> bool:
    """Compara número, texto, dict (x/y/z, pitch/yaw/roll) e refs; ângulos módulo 360."""
    if isinstance(esperado, bool) or isinstance(lido, bool):
        return bool(esperado) == bool(lido)
    if isinstance(esperado, (int, float)):
        try:
            d = abs(float(lido) - float(esperado))
        except (TypeError, ValueError):
            return False
        return d <= tol or abs(d - 360) <= tol
    if isinstance(esperado, dict):
        if "refPath" in esperado:
            return _ref(esperado) == _ref(lido)
        return isinstance(lido, dict) and all(_igual(v, lido.get(k), tol) for k, v in esperado.items())
    return str(esperado) == str(lido)


def _bounds(a: dict) -> dict:
    b = cliente().call(ACTOR, "get_actor_bounds", actor=a)
    mn, mx = b["min"], b["max"]
    return {"min": [mn["x"], mn["y"], mn["z"]], "max": [mx["x"], mx["y"], mx["z"]]}


def _chao_sob(x: float, y: float, z_topo: float, alcance: float = 3000) -> float | None:
    """Altura do primeiro piso abaixo de (x, y), partindo de z_topo. trace_world não acerta personagens."""
    d = cliente().call(SCENE, "trace_world", start={"x": x, "y": y, "z": z_topo}, end={"x": x, "y": y, "z": z_topo - alcance})
    return None if d is None else z_topo - float(d)


def _medir(a: dict, vizinhos: list | None = None) -> dict:
    b = _bounds(a)
    (x0, y0, z0), (x1, y1, z1) = b["min"], b["max"]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    piso = _chao_sob(cx, cy, z1 + 5)
    m = {"bounds": b, "centro_xy": [round(cx, 1), round(cy, 1)], "altura": round(z1 - z0, 1),
         "largura_max": round(max(x1 - x0, y1 - y0), 1), "piso_z": None if piso is None else round(piso, 1),
         "gap_chao": None if piso is None else round(z0 - piso, 1)}
    m["deitado"] = m["altura"] < 110 and m["largura_max"] > 120
    if vizinhos is not None:
        sob = []
        for v in vizinhos:
            if v["refPath"] == a["refPath"]:
                continue
            vb = _bounds(v)
            ix = min(x1, vb["max"][0]) - max(x0, vb["min"][0])
            iy = min(y1, vb["max"][1]) - max(y0, vb["min"][1])
            iz = min(z1, vb["max"][2]) - max(z0, vb["min"][2])
            if ix > 2 and iy > 2 and iz > 2:
                sob.append({"com": v["refPath"].split(".")[-1], "cm": [round(ix, 1), round(iy, 1), round(iz, 1)]})
        m["sobreposicoes"] = sob
    return m


def _vizinhos_proximos(a: dict, raio: float = 250) -> list:
    b = _bounds(a)
    cx, cy, cz = [(b["min"][i] + b["max"][i]) / 2 for i in range(3)]
    out = []
    for v in _skeletal_actors():
        if v["refPath"] == a["refPath"]:
            continue
        vb = _bounds(v)
        vx, vy, vz = [(vb["min"][i] + vb["max"][i]) / 2 for i in range(3)]
        if ((vx - cx) ** 2 + (vy - cy) ** 2 + (vz - cz) ** 2) ** 0.5 < raio:
            out.append(v)
    return out


def _captura(cam: dict, rot: dict):
    cap = cliente().call(APP, "CaptureViewport", captureTransform={"location": cam, "rotation": rot, "scale": {"x": 1, "y": 1, "z": 1}},
                         annotations={"gridSpacing": 0, "maxLabelDistance": 0})
    data = cap["image"]["data"] if isinstance(cap, dict) and "image" in cap else cap["returnValue"]["image"]["data"]
    return base64.b64decode(data)


def _base_mundo(a: dict) -> tuple:
    """Posição do personagem no mundo: ator + deslocamento do componente (os atores do LAB guardam a posição no componente)."""
    import math
    xf = cliente().call(ACTOR, "get_actor_transform", actor=a)
    rl = _props(a, ["relativeLocation"])["relativeLocation"]
    raiz = cliente().call(ACTOR, "get_root_component", actor=a)
    if _ref(raiz).endswith(COMP):  # o componente animado é a raiz: a posição dele já é a do ator
        return xf["location"]["x"], xf["location"]["y"], xf["location"]["z"]
    yaw = math.radians(xf["rotation"]["yaw"])
    x = xf["location"]["x"] + rl["x"] * math.cos(yaw) - rl["y"] * math.sin(yaw)
    y = xf["location"]["y"] + rl["x"] * math.sin(yaw) + rl["y"] * math.cos(yaw)
    return x, y, xf["location"]["z"] + rl["z"]


def _abertura(mask, n: int = 1):
    """Abertura morfológica 3x3 (erode n vezes e dilata n vezes): apaga pontos soltos, mantém regiões sólidas."""
    import numpy as np
    m = mask.copy()
    for op in (np.logical_and, np.logical_or):
        for _ in range(n):
            p = np.pad(m, 1, constant_values=(op is np.logical_or) and False)
            acc = p[1:-1, 1:-1].copy()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    acc = op(acc, p[1 + dy:p.shape[0] - 1 + dy, 1 + dx:p.shape[1] - 1 + dx])
            m = acc
    return m


def _silhueta(a: dict, vista: str = "frontal", salvar: str = "", mascara_pernas: bool = False,
              aquecer: bool = True) -> dict:
    """Mede a pose pela IMAGEM (a caixa envolvente não acompanha a pose dos clipes da biblioteca): captura com e
    sem o personagem (só ele some); a diferença em pixels cor de Y Bot é a silhueta. Projeta o piso e a marca de
    180 cm na mesma câmera para converter pixels em cm."""
    import io
    import math
    import numpy as np
    from PIL import Image
    x, y, z = _base_mundo(a)
    piso = _chao_sob(x, y, z + 150)
    piso = z if piso is None else piso
    rot_c = _props(a, ["relativeRotation"])["relativeRotation"]
    xf = cliente().call(ACTOR, "get_actor_transform", actor=a)
    frente = math.radians(rot_c["yaw"] + xf["rotation"]["yaw"] + 90 + {"frontal": 0, "lateral": 90}[vista])
    # Câmera um pouco acima, olhando para baixo: o fundo atrás do boneco é piso/parede, não o céu (que se mexe).
    dist = 420.0
    cam = {"x": x + dist * math.cos(frente), "y": y + dist * math.sin(frente), "z": piso + 170}
    alvo = (x, y, piso + 90)
    dx, dy, dz = alvo[0] - cam["x"], alvo[1] - cam["y"], alvo[2] - cam["z"]
    rot = {"pitch": math.degrees(math.atan2(dz, math.hypot(dx, dy))), "yaw": math.degrees(math.atan2(dy, dx)), "roll": 0}
    cliente().call(APP, "SetCameraTransform", transform={"location": cam, "rotation": rot})
    # Régua vertical: projeção de alturas de -30 a 240 cm na linha vertical da base do personagem.
    regua = []
    for zc in range(-30, 241, 30):
        q = cliente().call(APP, "WorldPosToScreenCoords", position={"x": x, "y": y, "z": piso + zc})
        if isinstance(q, dict):
            regua.append((zc, q["x"], q["y"]))
    comp = {"refPath": a["refPath"] + COMP}
    sombra = _props(a, ["castShadow"]).get("castShadow", True)
    try:  # sem sombra só durante a medida (a sombra no piso seria lida como pés)
        cliente().call(OBJECT, "set_properties", instance=comp, values=json.dumps({"castShadow": False}))
        time.sleep(0.2)
        if aquecer:  # 06/10 (Astra): a 1a captura depois de mexer na cópia saía instável (-18 cm, depois +0,2)
            _captura(cam, rot)
        com = _captura(cam, rot)
        cliente().call(OBJECT, "set_properties", instance=comp, values=json.dumps({"bVisible": False}))
        time.sleep(0.3)
        sem1 = _captura(cam, rot)
        sem2 = _captura(cam, rot)
    finally:
        cliente().call(OBJECT, "set_properties", instance=comp, values=json.dumps({"bVisible": True, "castShadow": sombra}))
    A, B1, B2 = (np.asarray(Image.open(io.BytesIO(b)).convert("RGB")).astype(int) for b in (com, sem1, sem2))
    h, w, _ = A.shape
    out = {"camera": cam, "piso_z": round(piso, 1)}
    if len(regua) < 5:
        out["medido"] = False
        return out
    zs = np.array([r[0] for r in regua], float)
    ry = np.array([r[2] for r in regua], float) * h          # y em pixels cresce para baixo; z cresce para cima
    rx = np.array([r[1] for r in regua], float) * w
    px_por_cm = abs(ry[0] - ry[-1]) / (zs[-1] - zs[0])
    ruido = np.abs(B1 - B2).sum(axis=2) > 30                   # o que muda sem o boneco é fundo animado
    mask = (np.abs(A - B1).sum(axis=2) > 45) & ~ruido
    # Janela: 70 cm para cada lado da linha da base, de -30 a 240 cm de altura.
    x0, x1 = int(max(0, rx.mean() - 70 * px_por_cm)), int(min(w, rx.mean() + 70 * px_por_cm))
    y0, y1 = int(max(0, ry.min())), int(min(h, ry.max()))
    roi = np.zeros_like(mask)
    roi[y0:y1, x0:x1] = True
    mask &= roi
    mask = _abertura(mask, 2)
    out["pixels"] = int(mask.sum())
    if salvar:
        Image.fromarray((mask * 255).astype("uint8")).save(salvar)
    if mask.sum() < 300:
        out["medido"] = False
        return out
    ys, xs = np.nonzero(mask)
    # remove pixels soltos: usa os percentis 0,2 e 99,8 em vez de min/max
    top, bot = np.percentile(ys, 0.2), np.percentile(ys, 99.8)
    esq, dir_ = np.percentile(xs, 0.5), np.percentile(xs, 99.5)
    ordem = np.argsort(ry)                                     # interpolar altura a partir do pixel y
    altura_de = lambda py: float(np.interp(py, ry[ordem], zs[ordem]))
    # Calibração (05/10, work/calibracao_silhueta.json): com esta câmera, pés no piso medem -9 cm (perspectiva).
    area = float(mask.sum()) / (px_por_cm ** 2)
    out.update({"px_por_cm": round(float(px_por_cm), 2), "area_cm2": round(area)})
    linha80 = int(np.interp(80.0, zs, ry))  # pixel y da altura 80 cm (zs crescente na régua)
    area_pernas = float(mask[max(0, linha80):, :].sum()) / (px_por_cm ** 2)
    out["area_pernas_cm2"] = round(area_pernas)
    if area < AREA_MIN_CM2 or px_por_cm < 1.0 or area_pernas < PERNAS_MIN_CM2:  # máscara incompleta: não mede (06/10)
        out["medido"] = False
        out["motivo"] = (f"silhueta incompleta (área {area:.0f} cm2, pernas {area_pernas:.0f} cm2, "
                         f"{px_por_cm:.2f} px/cm)")
        return out
    out.update({"medido": True, "altura_cm": round(altura_de(top), 1), "gap_pes_cm": round(altura_de(bot) + CALIB_PES_CM, 1),
                "largura_cm": round(float((dir_ - esq) / px_por_cm), 1),
                "centro_desvio_cm": round(float(((esq + dir_) / 2 - rx.mean()) / px_por_cm), 1)})
    out["deitado"] = bool(out["altura_cm"] < 110 and out["largura_cm"] > out["altura_cm"])
    if mascara_pernas:  # região abaixo de 80 cm, para comparar pernas entre instantes (pés plantados?)
        linha = int(np.interp(80.0, zs, ry))
        out["_pernas"] = mask[linha:, :].copy()
    return out


ESTUDIO = (10000.0, -3000.0)  # "dimensão paralela": zona neutra longe da sala; atores TESTE_ESTUDIO_* temporários
_estudio = {"piso": None}


def _xf(x, y, z, pitch=0.0, yaw=0.0, roll=0.0, s=(1, 1, 1)) -> dict:
    return {"location": {"x": x, "y": y, "z": z}, "rotation": {"pitch": pitch, "yaw": yaw, "roll": roll},
            "scale": {"x": s[0], "y": s[1], "z": s[2]}}


# Estúdio v2 (06/10): sala técnica fechada. O céu azul e as nuvens tinham a cor do mannequin (ciano) e atrapalhavam
# a silhueta e a visão. Paredes e teto: cinza escuro SEM iluminação (emitem a própria cor: tom fixo em qualquer
# vista, sem ficar preto). Piso: cinza médio fosco e iluminado (mostra a sombra de contato). Luz branca própria e
# exposição manual num volume de pós-processo (sem bloom, DOF, vinheta, motion blur, lens flare).
ESTUDIO_V2 = None  # None = decide pelo arquivo work/estudio_v2.on (liga sem reiniciar o Hermes); True/False força
PASTA_ESTUDIO = "/Game/_AnimLab/Estudio"
MAT = "editor_toolset.toolsets.material.MaterialTools"
COR_FUNDO = 0.035   # emissivo linear das paredes/teto (cinza escuro na imagem)
COR_PISO = 0.18     # albedo linear do piso (cinza médio)
MEIO, ALTO = 600.0, 700.0  # meia largura interna e altura da sala (cm)
EXPOSICAO = {"bOverride_AutoExposureMethod": True, "autoExposureMethod": "AEM_Manual",
             "bOverride_AutoExposureBias": True, "autoExposureBias": 0.0,
             "bOverride_AutoExposureApplyPhysicalCameraExposure": True, "autoExposureApplyPhysicalCameraExposure": False,
             "bOverride_BloomIntensity": True, "bloomIntensity": 0.0,
             "bOverride_DepthOfFieldEnabled": True, "depthOfFieldEnabled": False,
             "bOverride_MotionBlurAmount": True, "motionBlurAmount": 0.0,
             "bOverride_VignetteIntensity": True, "vignetteIntensity": 0.0,
             "bOverride_LensFlareIntensity": True, "lensFlareIntensity": 0.0,
             "bOverride_SceneFringeIntensity": True, "sceneFringeIntensity": 0.0}
LUZ_LUMENS = 80.0  # medido 06/10: 100 lm -> piso 153/255; 0 lm -> 62 (vazamento)


def _material_estudio(nome: str, cor: float, sem_luz: bool) -> str:
    """Cria (uma vez) um material cinza constante em /Game/_AnimLab/Estudio e o salva. Devolve o refPath."""
    ref = f"{PASTA_ESTUDIO}/{nome}.{nome}"
    achados = cliente().call(ASSET, "find_assets", folder_path=PASTA_ESTUDIO, name=nome) or []
    if any(_ref(x).split(".")[0] == f"{PASTA_ESTUDIO}/{nome}" for x in achados):
        sm = json.loads(cliente().call(OBJECT, "get_properties", instance={"refPath": ref}, properties=["ShadingModel"]))
        if (sm.get("ShadingModel") == "MSM_Unlit") != sem_luz:
            raise UnrealError(f"material {nome} existe com sombreamento errado ({sm}); peça ao operador")
        return ref
    cliente().call(MAT, "create_material", folder_path=PASTA_ESTUDIO, asset_name=nome)
    m = {"refPath": ref}

    def const(classe, valor, saida, y):
        e = cliente().call(MAT, "add_expression", material_or_function=m, expression_class={"refPath": f"/Script/Engine.{classe}"}, x=-300, y=y)
        e = e if isinstance(e, dict) else {"refPath": e}
        cliente().call(OBJECT, "set_properties", instance=e, values=json.dumps({"R": valor} if classe.endswith("Constant") else
                                                                              {"Constant": {"R": valor, "G": valor, "B": valor, "A": 1}}))
        cliente().call(MAT, "connect_to_output", expression=e, output_name="", material_property=saida)

    if sem_luz:
        cliente().call(OBJECT, "set_properties", instance=m, values=json.dumps({"ShadingModel": "MSM_Unlit"}))
        const("MaterialExpressionConstant3Vector", cor, "MP_EmissiveColor", 0)
    else:
        const("MaterialExpressionConstant3Vector", cor, "MP_BaseColor", 0)
        const("MaterialExpressionConstant", 1.0, "MP_Roughness", 150)
        const("MaterialExpressionConstant", 0.0, "MP_Specular", 300)
    cliente().call(MAT, "recompile", material_or_function=m)
    cliente().call(ASSET, "save_assets", asset_paths=[f"{PASTA_ESTUDIO}/{nome}"])
    return ref


def _spawn_estudio(nome: str, xform: dict, asset: str = "", classe: str = "") -> dict:
    if asset:
        a = cliente().call(SCENE, "add_to_scene_from_asset", asset_path=asset, name=f"TESTE_ESTUDIO_{RUN}_{nome}", xform=xform)
    else:
        a = cliente().call(SCENE, "add_to_scene_from_class", actor_type={"refPath": classe}, name=f"TESTE_ESTUDIO_{RUN}_{nome}", xform=xform)
    a = a if isinstance(a, dict) else {"refPath": a}
    cliente().call(ACTOR, "set_label", actor=a, label=f"TESTE_ESTUDIO_{RUN}_{nome}")
    _estudio.setdefault("atores", []).append(a)
    return a


COR_SILHUETA = 1.0      # emissivo da cópia de medição: branco SEM iluminação (contraste não depende do Lumen)
AREA_MIN_CM2 = 2500.0   # silhueta de um corpo inteiro tem ~4000-7000 cm2; abaixo disso a máscara está incompleta
PERNAS_MIN_CM2 = 800.0  # pernas de pé (abaixo de 80 cm) ~1500-2500 cm2; sem pernas = máscara parcial (Astra)
AJUSTE_MAX_CM = 10.0    # ajuste de Z maior que isto = pose sem chão / sentada / medida ruim: reprova, não "conserta"


def _pintar_copia(copia: dict):
    """Na v2, a cópia de medição recebe material branco sem iluminação (06/10: com o Unreal em segundo plano o Lumen
    não convergia, o boneco escurecia, a silhueta perdia as pernas e a macro afundava o ator ~25 cm)."""
    v2 = ESTUDIO_V2 if ESTUDIO_V2 is not None else os.path.exists(os.path.join(RAIZ_WORK, "estudio_v2.on"))
    if not v2:
        return
    m = _material_estudio("M_Estudio_Silhueta", COR_SILHUETA, sem_luz=True)
    malha = _ref(_props(copia, ["skeletalMeshAsset"]).get("skeletalMeshAsset")) or MALHA_YBOT
    n = len(cliente().call(SKMESH, "get_material_slots", mesh={"refPath": malha}) or []) or 2
    cliente().call(OBJECT, "set_properties", instance={"refPath": copia["refPath"] + COMP},
                   values=json.dumps({"overrideMaterials": [{"refPath": m}] * n}))


def _estudio_piso():
    """Monta a sala técnica do estúdio (uma vez por processo) e devolve o piso (topo em z=0)."""
    v2_pedido = ESTUDIO_V2 if ESTUDIO_V2 is not None else os.path.exists(os.path.join(RAIZ_WORK, "estudio_v2.on"))
    if _estudio["piso"] and _estudio.get("versao") == ("v2" if v2_pedido else "v1"):
        return _estudio["piso"]
    if _estudio["piso"] or _estudio.get("atores"):  # versão mudou ou montagem anterior incompleta: desmonta
        limpar_estudio()
    v2 = ESTUDIO_V2 if ESTUDIO_V2 is not None else os.path.exists(os.path.join(RAIZ_WORK, "estudio_v2.on"))
    if not v2:  # v1: só o piso (céu ao fundo)
        p = cliente().call(SCENE, "add_to_scene_from_asset", asset_path="/Engine/BasicShapes/Cube.Cube",
                           name=f"TESTE_ESTUDIO_{RUN}_PISO", xform=_xf(ESTUDIO[0], ESTUDIO[1], -50, s=(12, 12, 1)))
        p = p if isinstance(p, dict) else {"refPath": p}
        cliente().call(ACTOR, "set_label", actor=p, label=f"TESTE_ESTUDIO_{RUN}_PISO")
        _estudio.update(piso=p, versao="v1")
        return p
    fundo = _material_estudio("M_Estudio_Fundo", COR_FUNDO, sem_luz=True)
    chao = _material_estudio("M_Estudio_Piso", COR_PISO, sem_luz=False)
    X, Y = ESTUDIO
    L = 2 * MEIO / 100 + 2  # escala do cubo de 1 m que cobre a sala com sobra
    cubo = "/Engine/BasicShapes/Cube.Cube"
    pecas = {"PISO": (_xf(X, Y, -50, s=(L, L, 1)), chao),
             "TETO": (_xf(X, Y, ALTO + 50, s=(L, L, 1)), fundo),
             "PAREDE_XP": (_xf(X + MEIO + 50, Y, ALTO / 2, s=(1, L, ALTO / 100 + 2)), fundo),
             "PAREDE_XN": (_xf(X - MEIO - 50, Y, ALTO / 2, s=(1, L, ALTO / 100 + 2)), fundo),
             "PAREDE_YP": (_xf(X, Y + MEIO + 50, ALTO / 2, s=(L, 1, ALTO / 100 + 2)), fundo),
             "PAREDE_YN": (_xf(X, Y - MEIO - 50, ALTO / 2, s=(L, 1, ALTO / 100 + 2)), fundo)}
    for nome, (xf, mat) in pecas.items():
        a = _spawn_estudio(nome, xf, asset=cubo)
        comp = cliente().call(ACTOR, "get_root_component", actor=a)
        comp = comp if isinstance(comp, dict) else {"refPath": comp}
        cliente().call(OBJECT, "set_properties", instance=comp, values=json.dumps({"overrideMaterials": [{"refPath": mat}]}))
        if nome == "PISO":
            piso_v2 = a
    luz = _spawn_estudio("LUZ", _xf(X, Y, ALTO - 20, pitch=-90), classe="/Script/Engine.RectLight")
    lc = cliente().call(ACTOR, "get_root_component", actor=luz)
    cliente().call(OBJECT, "set_properties", instance=lc if isinstance(lc, dict) else {"refPath": lc}, values=json.dumps({
        "intensityUnits": "Lumens", "Intensity": LUZ_LUMENS, "SourceWidth": 500, "sourceHeight": 500,
        "AttenuationRadius": 2500, "barnDoorAngle": 88, "lightColor": {"r": 1, "g": 1, "b": 1, "a": 1}, "castShadows": True}))
    ppv = _spawn_estudio("POS", _xf(X, Y, ALTO / 2, s=(MEIO / 100, MEIO / 100, ALTO / 200)), classe="/Script/Engine.PostProcessVolume")
    cliente().call(OBJECT, "set_properties", instance=ppv, values=json.dumps({"bUnbound": False, "priority": 100, "settings": EXPOSICAO}))
    cliente().call(APP, "SelectActors", actors=[])  # o contorno de seleção (ciano) sujava as capturas
    time.sleep(1.0)
    _estudio.update(piso=piso_v2, versao="v2")  # só marca pronto no fim (Astra: montagem incompleta era reutilizada)
    return piso_v2


def limpar_estudio(todos: bool = False):
    """Remove o piso e cópias DESTA execução (TESTE_ESTUDIO_<RUN>_*); todos=True remove resíduos de qualquer execução."""
    prefixo = "TESTE_ESTUDIO_" if todos else f"TESTE_ESTUDIO_{RUN}_"
    for a in cliente().call(SCENE, "find_actors", name="", tag="", collision_channels=["ObjectTypeQuery1"]) or []:
        try:
            if str(cliente().call(ACTOR, "get_label", actor=a)).startswith(prefixo):
                cliente().call(SCENE, "remove_from_scene", actor=a)
        except UnrealError:
            pass
    _estudio["piso"] = None
    _estudio["atores"] = []


def _amostrar_estudio(a: dict, vista: str = "lateral", n: int = 4, intervalo: float = 0.6) -> list:
    """Uma única cópia no estúdio, tocando o loop; n silhuetas em instantes diferentes (para medir deriva)."""
    p = _props(a, ["skeletalMeshAsset", "animationMode", "animationData", "relativeRotation"])
    xf = cliente().call(ACTOR, "get_actor_transform", actor=a)
    rot = p["relativeRotation"]
    dados = dict(p["animationData"])
    dados.update({"bSavedPlaying": True, "bSavedLooping": True, "savedPlayRate": 1.0})
    _estudio_piso()
    copia = cliente().call(SCENE, "add_to_scene_from_class", actor_type={"refPath": "/Script/Engine.SkeletalMeshActor"},
                           name="TESTE_ESTUDIO_COPIA", xform=_xf(ESTUDIO[0], ESTUDIO[1], 0))
    copia = copia if isinstance(copia, dict) else {"refPath": copia}
    out = []
    try:
        cliente().call(ACTOR, "set_label", actor=copia, label=f"TESTE_ESTUDIO_{RUN}_COPIA")
        cliente().call(OBJECT, "set_properties", instance={"refPath": copia["refPath"] + COMP}, values=json.dumps({
            "skeletalMeshAsset": {"refPath": _ref(p["skeletalMeshAsset"]) or MALHA_YBOT},
            "animationMode": "AnimationSingleNode", "bUseRefPoseOnInitAnim": False,
            "relativeRotation": {"pitch": rot["pitch"], "yaw": rot["yaw"] + xf["rotation"]["yaw"], "roll": rot["roll"]},
            "animationData": dados}))
        _pintar_copia(copia)
        # O editor não toca o loop em tempo real de forma confiável: congela a cópia em instantes do clipe.
        anim_ref = _ref(dados.get("animToPlay"))
        duracao = duracao_clipe(anim_ref)
        for i in range(n):
            t_i = round(duracao * i / n, 3)
            cliente().call(OBJECT, "set_properties", instance={"refPath": copia["refPath"] + COMP}, values=json.dumps({
                "animationData": {"animToPlay": {"refPath": anim_ref}, "savedPosition": t_i, "savedPlayRate": 0.0,
                                  "bSavedLooping": False, "bSavedPlaying": False}}))
            time.sleep(intervalo)
            s = _silhueta(copia, vista=vista, mascara_pernas=True)
            s["t"] = t_i
            out.append(s)
    finally:
        cliente().call(SCENE, "remove_from_scene", actor=copia)
    return out


def duracao_clipe(anim_ref: str) -> float:
    """Duração em segundos: pelo índice da biblioteca (30 fps) ou, para clipes do site, 2 s (sem leitura no MCP)."""
    from . import catalogo
    nome = anim_ref.split("/")[-1].split(".")[0]
    for sufixo in ("_Anim",):
        if nome.endswith(sufixo):
            nome = nome[: -len(sufixo)]
    for it in catalogo._indice():
        if it["nome"] == nome:
            return max(0.5, it["quadros"] / 30.0)
    return 2.0


def _silhueta_estudio(a: dict) -> dict:
    """Mede a pose numa CÓPIA do personagem no estúdio: mesma malha, animação e rotação, fundo neutro, ninguém na
    frente, original intocado. gap_local_cm = onde os pés ficariam em relação ao piso REAL sob o original."""
    p = _props(a, ["skeletalMeshAsset", "animationMode", "animationData", "relativeRotation"])
    xf = cliente().call(ACTOR, "get_actor_transform", actor=a)
    rot = p["relativeRotation"]
    _estudio_piso()
    copia = cliente().call(SCENE, "add_to_scene_from_class", actor_type={"refPath": "/Script/Engine.SkeletalMeshActor"},
                           name="TESTE_ESTUDIO_COPIA", xform=_xf(ESTUDIO[0], ESTUDIO[1], 0))
    copia = copia if isinstance(copia, dict) else {"refPath": copia}
    try:
        cliente().call(ACTOR, "set_label", actor=copia, label=f"TESTE_ESTUDIO_{RUN}_COPIA")
        cliente().call(OBJECT, "set_properties", instance={"refPath": copia["refPath"] + COMP}, values=json.dumps({
            "skeletalMeshAsset": {"refPath": _ref(p["skeletalMeshAsset"]) or MALHA_YBOT},
            "animationMode": p.get("animationMode") or "AnimationSingleNode", "bUseRefPoseOnInitAnim": False,
            "relativeRotation": {"pitch": rot["pitch"], "yaw": rot["yaw"] + xf["rotation"]["yaw"], "roll": rot["roll"]},
            "animationData": p["animationData"]}))
        _pintar_copia(copia)
        time.sleep(0.6)
        s = _silhueta(copia)
        if s.get("medido") and abs(s["gap_pes_cm"]) > 2.0:  # vai pedir ajuste ou reprovar: confirma antes (Astra)
            obs = [s]
            for _ in range(2):
                obs.append(_silhueta(copia, aquecer=False))
                par = [(x, y) for i, x in enumerate(obs) for y in obs[i + 1:]
                       if x.get("medido") and y.get("medido") and abs(x["gap_pes_cm"] - y["gap_pes_cm"]) <= 2.0
                       and abs(x["altura_cm"] - y["altura_cm"]) <= 3.0]
                if par:
                    s = par[0][1]
                    break
            else:
                s = dict(s, medido=False, motivo="medição instável: gaps " + str([o.get("gap_pes_cm") for o in obs]))
            s["observacoes_gap"] = [o.get("gap_pes_cm") for o in obs]
    finally:
        cliente().call(SCENE, "remove_from_scene", actor=copia)
    s["fonte"] = "estudio"
    if s.get("medido"):
        x, y, z = _base_mundo(a)
        piso = _chao_sob(x, y, z + 150)
        s["piso_local_z"] = None if piso is None else round(piso, 1)
        s["gap_local_cm"] = None if piso is None else round(z + s["gap_pes_cm"] - piso, 1)
    return s


# ---------- macros somente leitura ----------

@macro
def inspecionar_cena(rel, filtro: str = ""):
    """Lista os personagens (SkeletalMeshActor) com rótulo, posição, animação, flags e medidas."""
    lista = []
    for a in _skeletal_actors():
        nome = a["refPath"].split(".")[-1]
        lab = _label(a)
        if filtro and filtro.lower() not in (nome + " " + lab).lower():
            continue
        p = _props(a)
        m = _medir(a)
        anim = _ref((p.get("animationData") or {}).get("animToPlay"))
        lista.append({"nome": nome, "rotulo": lab,
                      "comp_loc": p.get("relativeLocation"), "comp_rot": p.get("relativeRotation"),
                      "modo": p.get("animationMode"), "anim": anim.split(".")[-1],
                      "tempo": (p.get("animationData") or {}).get("savedPosition"),
                      "loop": (p.get("animationData") or {}).get("bSavedLooping"),
                      "refpose_init": p.get("bUseRefPoseOnInitAnim"),
                      "caixa_altura": m["altura"], "caixa_gap_chao": m["gap_chao"], "centro_xy": m["centro_xy"]})
    rel["medidas"]["personagens"] = lista
    rel["medidas"]["level"] = cliente().call(SCENE, "get_current_level")
    rel["avisos"].append("caixa_* vem da caixa envolvente do Unreal, que NÃO acompanha a pose dos clipes da biblioteca: "
                         "para julgar pose ou pés no chão use medir_personagem (silhueta).")


def _vizinhos_bases(a: dict, raio: float = 250) -> list:
    """Distância (cm, no plano) da base deste personagem às bases dos outros dentro do raio."""
    x, y, z = _base_mundo(a)
    out = []
    for v in _skeletal_actors():
        if v["refPath"] == a["refPath"]:
            continue
        vx, vy, vz = _base_mundo(v)
        d = ((vx - x) ** 2 + (vy - y) ** 2) ** 0.5
        if d < raio and abs(vz - z) < 150:
            out.append({"com": v["refPath"].split(".")[-1], "dist_cm": round(d, 1)})
    return sorted(out, key=lambda r: r["dist_cm"])


@macro
def medir_personagem(rel, ator: str, com_vizinhos: bool = True, distancia_minima_cm: float = 45.0):
    """Mede um personagem de pé pela silhueta (altura, pés no chão, deitado) e a distância às bases dos vizinhos."""
    a = resolver_ator(ator)
    s = _silhueta_estudio(a)
    rel["medidas"]["silhueta"] = s
    rel["medidas"]["props"] = _props(a)
    gs = [gates.silhueta_de_pe(s), gates.pes_no_chao({"gap_chao": s.get("gap_local_cm")}, 4.0)]
    if com_vizinhos:
        viz = _vizinhos_bases(a)
        rel["medidas"]["vizinhos"] = viz
        perto = [v for v in viz if v["dist_cm"] < distancia_minima_cm]
        gs.append(gates.g("distancia_vizinhos", not perto, viz[:3], f">= {distancia_minima_cm} cm entre bases"))
    rel["medidas"]["gates"] = gs


# ---------- macros que mudam a cena ----------

@macro
def importar_clipe(rel, nome: str):
    """Importa um clipe da biblioteca Mixamo (versão com malha do Y Bot) para /Game/_AnimLab/Mixamo, sem duplicar."""
    anim = _achar_anim(nome)
    if anim:
        rel["medidas"].update({"anim": anim, "ja_existia": True})
        return
    fbx = os.path.join(BIBLIOTECA, "animation_motion_ybot", nome + ".fbx")
    if not os.path.exists(fbx):
        raise FileNotFoundError(f"clipe não está na biblioteca: {nome} (use buscar_clipe)")
    cliente().call(SKMESH, "import_file", folder_path=PASTA_CLIPES, asset_name=nome,
                   source_file=fbx.replace("\\", "/"), skeleton={"refPath": ESQUELETO}, import_animations=True)
    anim = _achar_anim(nome)
    if not anim:
        raise UnrealError(f"import não gerou animação para {nome}")
    rel["medidas"].update({"anim": anim, "ja_existia": False})


def familia_clipe(anim: str) -> str:
    """'site' = FBX baixado do mixamo.com (asset ..._mixamo_com): sem correção.
    'biblioteca' = importado de animation_motion_ybot: o export pelo Blender deita o corpo 90 graus; o componente
    precisa de roll +90 (validado em 05/10: fica de pé, olha +Y no yaw 0 e compõe com o yaw)."""
    from . import catalogo
    base = anim.split(".")[-1]
    if base.endswith("_mixamo_com"):
        return "site"
    if anim.startswith(PASTA_CLIPES + "/") and base.endswith("_Anim") and \
            base[:-5] in {it["nome"] for it in catalogo._indice()}:
        return "biblioteca"
    raise ValueError(f"família do clipe desconhecida ({anim}): só clipes do site (..._mixamo_com) ou da biblioteca "
                     "importados por importar_clipe")


def _achar_anim(nome: str) -> str | None:
    """Só o nome exato <nome>_Anim gerado por importar_clipe (nada de 'começa com')."""
    alvo = f"{nome}_Anim"
    for p in cliente().call(ASSET, "find_assets", folder_path=PASTA_CLIPES, name=nome) or []:
        if p.split("/")[-1] == alvo:
            return f"{p}.{alvo}"
    return None


@macro
def aplicar_clipe(rel, ator: str, clipe: str, loop: bool = True, tempo: float = 0.0,
                  corrigir_altura: bool = True, tolerancia_cm: float = 4.0, manter_se_falhar: bool = False,
                  checar_movimento: bool = True):
    """Aplica um clipe num personagem DE PÉ sem mover o ator. Corrige a orientação dos clipes da biblioteca (roll 90,
    FALHA-20), mede a pose pela silhueta de uma cópia no estúdio e, se os pés não estiverem no piso, ajusta só o Z do
    componente e MEDE DE NOVO. checar_movimento: mede também 4 instantes do clipe (de lado) e exige pose de pé em
    todos e pernas plantadas (06/10: um instante só deixava passar caminhada, queda e transição para sentar).
    Se qualquer gate reprovar ou der erro, restaura o estado anterior e confere."""
    a = resolver_ator(ator)
    _checar_suportado(a)
    anim = clipe if clipe.startswith("/Game/") else _achar_anim(clipe)
    if not anim:
        raise ValueError(f"clipe não importado: {clipe} (rode importar_clipe)")
    xf_antes = cliente().call(ACTOR, "get_actor_transform", actor=a)
    antes = _props(a)
    rel["medidas"]["antes"] = {"props": antes, "ator": xf_antes}
    fam = familia_clipe(anim)
    rot = dict(antes["relativeRotation"])
    rot["roll"] = 90.0 if fam == "biblioteca" else 0.0
    rel["medidas"]["familia"] = fam
    try:
        _aplicar_e_medir(rel, a, anim, antes, xf_antes, rot, loop, tempo, corrigir_altura, tolerancia_cm)
        if checar_movimento and all(g["resultado"] == "PASS" for g in rel["medidas"]["gates"]):
            amostras = _amostrar_estudio(a, vista="lateral", n=4)
            rel["medidas"]["amostras"] = [{k: s.get(k) for k in ("t", "medido", "altura_cm", "gap_pes_cm", "motivo")}
                                          for s in amostras]
            rel["medidas"]["gates"] += [gates.pose_em_todo_clipe(amostras), gates.pes_plantados(amostras)]
    except Exception:
        rel["medidas"]["restaurado"] = _restaurar(a, antes)
        raise
    if not all(g["resultado"] == "PASS" for g in rel["medidas"]["gates"]) and not manter_se_falhar:
        rel["medidas"]["restaurado"] = _restaurar(a, antes)
        if not rel["medidas"]["restaurado"]:
            rel["avisos"].append("ESTADO PARCIAL: a restauração não conferiu; avise o operador")


def _checar_suportado(a: dict):
    """A cópia do estúdio só reproduz atores sem escala e sem inclinação (A06): recusa o resto."""
    xf = cliente().call(ACTOR, "get_actor_transform", actor=a)
    p = _props(a, ["relativeScale3D", "relativeRotation"])
    esc = [xf["scale"][k] for k in "xyz"] + [p["relativeScale3D"][k] for k in "xyz"]
    roll_ator = xf["rotation"]["roll"]
    if _ref(cliente().call(ACTOR, "get_root_component", actor=a)).endswith(COMP):
        roll_ator = 0.0  # componente é a raiz: o roll do ator É o roll 0/90 que a própria macro escreve
    if any(abs(v - 1) > 1e-3 for v in esc) or abs(xf["rotation"]["pitch"]) > 0.5 or abs(roll_ator) > 0.5 \
            or abs(p["relativeRotation"]["pitch"]) > 0.5:
        raise ValueError("ator com escala ou inclinação: não suportado pelas medidas do estúdio (peça ao operador)")


def _restaurar(a: dict, antes: dict) -> bool:
    """Escreve de volta o estado anterior e confere animação, modo, posição e rotação. True se conferiu."""
    try:
        vals = {k: antes[k] for k in ("animationMode", "bUseRefPoseOnInitAnim", "relativeLocation", "relativeRotation") if k in antes}
        cliente().call(OBJECT, "set_properties", instance={"refPath": a["refPath"] + COMP}, values=json.dumps(vals))
        if "animationData" in antes:
            cliente().call(OBJECT, "set_properties", instance={"refPath": a["refPath"] + COMP},
                           values=json.dumps({"animationData": antes["animationData"]}))
        lido = _props(a)
        return all(_igual(antes[k], lido.get(k)) for k in vals) and \
            _ref((antes.get("animationData") or {}).get("animToPlay")) == _ref((lido.get("animationData") or {}).get("animToPlay"))
    except Exception:
        return False


def _aplicar_e_medir(rel, a, anim, antes, xf_antes, rot, loop, tempo, corrigir_altura, tolerancia_cm):
    _set(a, {"animationMode": "AnimationSingleNode", "bUseRefPoseOnInitAnim": False, "relativeRotation": rot})
    cliente().call(OBJECT, "set_properties", instance={"refPath": a["refPath"] + COMP}, values=json.dumps({
        "animationData": {"animToPlay": {"refPath": anim}, "savedPosition": float(tempo),
                          "savedPlayRate": 1.0 if loop else 0.0, "bSavedLooping": bool(loop), "bSavedPlaying": bool(loop)}}))
    lido = _props(a, ["animationData"])["animationData"]
    if _ref(lido.get("animToPlay")) != anim:
        raise UnrealError(f"animToPlay não ficou: {lido}")
    time.sleep(0.6)
    # A pose é medida pela silhueta de uma CÓPIA no estúdio (a caixa envolvente não acompanha os clipes da
    # biblioteca; no estúdio ninguém fica na frente e o original não é tocado). Pés no piso real = conta.
    s = _silhueta_estudio(a)
    ajuste = 0.0
    precisa = corrigir_altura and s.get("medido") and s.get("gap_local_cm") is not None \
        and abs(s["gap_local_cm"]) > tolerancia_cm and not s["deitado"]
    if precisa and abs(s["gap_local_cm"]) > AJUSTE_MAX_CM:  # FALHA-25: não "conserta" pose sem chão afundando o ator
        rel["avisos"].append(f"pés a {s['gap_local_cm']:+.1f} cm do piso: acima do ajuste permitido ({AJUSTE_MAX_CM:.0f} cm); "
                             "pose sem chão, sentada ou medida ruim")
        precisa = False
    if precisa:
        loc = dict(antes["relativeLocation"])
        ajuste = -s["gap_local_cm"]
        loc["z"] = round(loc["z"] + ajuste, 2)
        _set(a, {"relativeLocation": loc})
        time.sleep(0.4)
        s = _silhueta_estudio(a)  # mede de novo: nada de PASS calculado (A05)
    s["ajuste_z_cm"] = round(ajuste, 1)
    rel["medidas"]["silhueta"] = s
    rel["medidas"]["anim"] = anim
    xf_depois = cliente().call(ACTOR, "get_actor_transform", actor=a)
    rel["medidas"]["gates"] = [gates.silhueta_de_pe(s), gates.pes_no_chao({"gap_chao": s.get("gap_local_cm")}, tolerancia_cm),
                               gates.ator_parado(xf_antes, xf_depois, ajuste_z=ajuste,
                                                 ajuste_roll=rot["roll"] - antes["relativeRotation"].get("roll", 0.0))]


@macro
def restaurar_animacao(rel, ator: str, estado: dict):
    """Volta animação, flags e posição do componente ao `estado` (o `medidas.antes.props` de aplicar_clipe)."""
    a = resolver_ator(ator)
    if not _restaurar(a, estado):
        raise UnrealError("restauração não conferiu (estado parcial); avise o operador")
    rel["medidas"]["props"] = _props(a)


@macro
def capturar_evidencia(rel, ator: str, vista: str = "frontal", nome: str = "", elevacao: float = 8.0):
    """Enquadra o personagem por projeção (corpo inteiro no quadro, cobertura >= 12%), confere oclusão por
    cenário e grava PNG em ULD_EVIDENCE_DIR. vista: frontal | lateral | traseira."""
    import math
    a = resolver_ator(ator)
    p = _props(a, ["relativeRotation"])
    xf = cliente().call(ACTOR, "get_actor_transform", actor=a)
    # Y Bot olha para +Y no yaw 0 (R-23): frente = yaw do componente + yaw do ator + 90.
    frente = p["relativeRotation"]["yaw"] + xf["rotation"]["yaw"] + 90 + {"frontal": 0, "lateral": 90, "traseira": 180}[vista]
    b = _bounds(a)
    mn, mx = [b["min"][i] - 10 for i in range(3)], [b["max"][i] + 10 for i in range(3)]
    c3 = [(mn[i] + mx[i]) / 2 for i in range(3)]
    cantos = [(x, y, z) for x in (mn[0], mx[0]) for y in (mn[1], mx[1]) for z in (mn[2], mx[2])]
    dist, log, achou = 250.0, [], None
    for _ in range(8):
        r = math.radians(frente)
        cam = {"x": c3[0] + dist * math.cos(r), "y": c3[1] + dist * math.sin(r), "z": c3[2] + dist * math.tan(math.radians(elevacao))}
        dx, dy, dz = c3[0] - cam["x"], c3[1] - cam["y"], c3[2] - cam["z"]
        rot = {"pitch": math.degrees(math.atan2(dz, math.hypot(dx, dy))), "yaw": math.degrees(math.atan2(dy, dx)), "roll": 0}
        cliente().call(APP, "SetCameraTransform", transform={"location": cam, "rotation": rot})
        pts = []
        for q in cantos:
            try:
                pts.append(cliente().call(APP, "WorldPosToScreenCoords", position={"x": q[0], "y": q[1], "z": q[2]}))
            except UnrealError:
                pts.append(None)
        if any(not isinstance(q, dict) for q in pts):
            dist *= 1.4
            continue
        xs, ys = [q["x"] for q in pts], [q["y"] for q in pts]
        bb = [min(xs), min(ys), max(xs), max(ys)]
        cob = (bb[2] - bb[0]) * (bb[3] - bb[1])
        log.append({"dist": round(dist), "cobertura": round(cob, 3)})
        if bb[0] < 0.03 or bb[1] < 0.03 or bb[2] > 0.97 or bb[3] > 0.97:
            dist *= 1.25
            continue
        if cob < 0.12:
            dist *= 0.8
            continue
        achou = (cam, rot, cob)
        break
    rel["medidas"]["enquadramento"] = log
    if not achou:
        rel["medidas"]["gates"] = [gates.g("enquadramento", False, None, "corpo inteiro e cobertura >= 0,12")]
        return
    cam, rot, cob = achou
    hit = cliente().call(SCENE, "trace_world", start=cam, end={"x": c3[0], "y": c3[1], "z": c3[2]})
    d = math.dist([cam["x"], cam["y"], cam["z"]], c3)
    ocl_ok = hit is None or float(hit) >= d - 60
    cap = cliente().call(APP, "CaptureViewport", captureTransform={"location": cam, "rotation": rot, "scale": {"x": 1, "y": 1, "z": 1}},
                         annotations={"gridSpacing": 0, "maxLabelDistance": 0})
    data = cap["image"]["data"] if isinstance(cap, dict) and "image" in cap else cap["returnValue"]["image"]["data"]
    png = base64.b64decode(data)
    if not png.startswith(b"\x89PNG"):
        raise UnrealError("captura não é PNG")
    nome = nome or f"{ator} - {vista}"
    arq = os.path.join(CENAS, f"{nome} - {dt.datetime.now():%H%M%S}.png")
    with open(arq, "wb") as f:
        f.write(png)
    rel["evidencias"].append(arq)
    rel["medidas"].update({"camera": cam, "rotacao": rot, "cobertura": round(cob, 3), "oclusao_cenario": not ocl_ok})
    rel["medidas"]["gates"] = [gates.g("enquadramento", True, round(cob, 3), ">= 0,12"),
                               gates.g("sem_oclusao_cenario", ocl_ok, hit, f"hit >= {round(d - 60)}")]


@macro
def chamada_avancada(rel, toolset: str, ferramenta: str, argumentos: dict, motivo: str):
    """ESCOTILHA: chama uma ferramenta atômica do MCP. Só quando nenhuma macro serve; o motivo fica registrado."""
    def log(evento: dict):
        os.makedirs(RAIZ_WORK, exist_ok=True)
        with open(os.path.join(RAIZ_WORK, "escotilha.log"), "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(evento, quando=dt.datetime.now().isoformat(timespec="seconds"), toolset=toolset,
                                    ferramenta=ferramenta, motivo=motivo, argumentos=str(argumentos)[:500]),
                               ensure_ascii=False) + "\n")
    if not motivo or len(motivo.strip()) < 15:
        log({"evento": "recusado", "razao": "motivo"})
        raise ValueError("explique o motivo (por que nenhuma macro serve)")
    if not any(ferramenta.startswith(p) for p in ESCOTILHA_LEITURA):
        log({"evento": "recusado", "razao": "não é leitura"})
        raise ValueError("a escotilha só permite LEITURA (get/find/list/describe/trace/Get*/WorldPos...). Para mudar a "
                         "cena use uma macro; se não existir, registre com registrar_falha que falta uma macro")
    log({"evento": "tentativa"})
    try:
        out = cliente().call(toolset, ferramenta, **argumentos)
    except Exception as e:
        log({"evento": "erro", "erro": str(e)[:300]})
        raise
    log({"evento": "ok", "resultado": str(out)[:300]})
    rel["medidas"]["resultado"] = out if len(str(out)) < 4000 else str(out)[:4000] + "...(cortado)"



@macro
def registrar_falha(rel, titulo: str, texto: str, estado: str = "ABERTO"):
    """Registra uma falha nova em work/FALHAS.md (numerada). Versão pública: arquivo local."""
    if len(titulo) < 8 or len(texto) < 20:
        raise ValueError("descreva título e texto (sintoma, causa ou hipótese, contorno)")
    arq = os.path.join(RAIZ_WORK, "FALHAS.md")
    atual = open(arq, encoding="utf-8").read() if os.path.exists(arq) else "# Falhas\n"
    n = 1 + max([int(x) for x in re.findall(r"^## FALHA-(\d+)", atual, re.M)] or [0])
    with open(arq, "a", encoding="utf-8") as f:
        f.write(f"\n## FALHA-{n:02d} — {titulo}\n- Estado: {estado} ({dt.date.today().isoformat()}).\n{texto.strip()}\n")
    rel["medidas"]["falha"] = f"FALHA-{n:02d}"


registrar_falha.__wrapped__._usa_unreal = False


@macro
def salvar_lab(rel):
    """Salva SÓ o level LAB_Animacao e os clipes importados em /Game/_AnimLab/Mixamo (nunca o esqueleto, a malha do
    Y Bot nem a sala). Use no fim de uma etapa aprovada."""
    alvos = ["/Game/_AnimLab/Maps/LAB_Animacao"]
    for p in cliente().call(ASSET, "find_assets", folder_path=PASTA_CLIPES, name="") or []:
        if not p.startswith(PROIBIDO_SALVAR) and cliente().call(ASSET, "is_dirty", asset_path=p):
            alvos.append(p)
    assert not any(a.startswith(PROIBIDO_SALVAR) for a in alvos)
    ok = cliente().call(ASSET, "save_assets", asset_paths=alvos)
    rel["medidas"].update({"salvos": alvos, "resultado": ok})
    if ok is False:
        rel["bloqueio"] = "save_assets recusou"
