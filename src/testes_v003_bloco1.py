"""v0.0.3 Bloco 1 — testes offline do DirectorTools (sem Unreal): o módulo carrega com `unreal` falso, toda ferramenta
está registrada e documentada (a Epic gera o schema da docstring), rótulo só casa exato, inventário não corta em 20
e a restauração é idempotente. O comportamento real é testado no Unreal (tools/bloco1_unreal.py)."""
import inspect
import json
import os
import sys
import types

AQUI = os.path.dirname(os.path.abspath(__file__))
EDITOR = os.path.join(AQUI, "..", "editor_python")
resultados = []


def caso(nome):
    def deco(fn):
        fn.nome = nome
        return fn
    return deco


class _Vec:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = x, y, z


class _Classe:
    def __init__(self, n):
        self.n = n

    def get_name(self):
        return self.n


class _Ator:
    def __init__(self, rotulo, classe="StaticMeshActor"):
        self.rotulo, self.classe = rotulo, classe

    def get_actor_label(self):
        return self.rotulo

    def get_class(self):
        return _Classe(self.classe)

    def get_path_name(self):
        return f"/Game/Lvl.Lvl:PersistentLevel.{self.rotulo}"

    def get_actor_location(self):
        return _Vec(1, 2, 3)

    def get_components_by_class(self, _):
        return []


ATORES = [_Ator(f"PC_{i:02d}", "SkeletalMeshActor") for i in range(25)] + [_Ator("Porta")]


def _unreal_falso():
    u = types.ModuleType("unreal")
    u.uclass = lambda: (lambda c: c)
    u.ToolsetDefinition = object
    u.EditorActorSubsystem = "EAS"
    u.UnrealEditorSubsystem = "UES"
    u.SkeletalMeshComponent = "SKC"

    class _EAS:
        def get_all_level_actors(self):
            return ATORES
    u.get_editor_subsystem = lambda k: _EAS()
    u.log = u.log_warning = u.log_error = print
    tr = types.ModuleType("toolset_registry")

    def tool_call(fn):
        fn._tool_call = True
        return fn
    tr.tool_call = tool_call
    reg = types.ModuleType("toolset_registry.registration")  # caminho real no UE 5.8 (não há tr.Registration)
    reg.Registration = lambda classes: types.SimpleNamespace(classes=classes, register=lambda: True)
    tr.registration = reg
    return u, tr, reg


def _carregar():
    u, tr, reg = _unreal_falso()
    sys.modules["unreal"], sys.modules["toolset_registry"], sys.modules["toolset_registry.registration"] = u, tr, reg
    sys.path.insert(0, os.path.abspath(EDITOR))
    for m in [m for m in sys.modules if m.startswith("director_tools")]:
        del sys.modules[m]
    import director_tools
    return director_tools


@caso("carrega com unreal falso e registra a classe DirectorTools")
def t_carrega():
    dt = _carregar()
    assert dt._registration.classes == [dt.DirectorTools]


@caso("toda ferramenta é tool_call + staticmethod, tem docstring com Returns e Args para cada parâmetro")
def t_contrato():
    dt = _carregar()
    nomes = []
    for nome, bruto in vars(dt.DirectorTools).items():
        fn = bruto.__func__ if isinstance(bruto, staticmethod) else bruto
        if getattr(bruto, "_tool_call", False) or getattr(fn, "_tool_call", False):
            assert isinstance(bruto, staticmethod), nome
            doc = inspect.getdoc(fn) or ""
            assert "Returns:" in doc, nome
            for p in inspect.signature(fn).parameters:
                assert f"{p}:" in doc, (nome, p)
            nomes.append(nome)
    assert set(nomes) == {"ping", "reload_toolset", "list_actors", "set_pose_eval", "bone_world_positions", "bone_position_in_clip",
                          "capture_isolated_setup", "capture_isolated_shot", "capture_isolated_restore", "seq_build", "clip_info", "seq_key_transform", "seq_eval_frame", "seq_close_delete"}, nomes


@caso("inventário não corta em 20 e filtra por classe e prefixo")
def t_inventario():
    dt = _carregar()
    todos = json.loads(dt.DirectorTools.list_actors())
    pcs = json.loads(dt.DirectorTools.list_actors(class_name="SkeletalMeshActor"))
    pref = json.loads(dt.DirectorTools.list_actors(label_prefix="PC_2"))
    assert todos["total"] == 26 and pcs["total"] == 25 and pref["total"] == 5, (todos["total"], pcs["total"], pref)


@caso("rótulo só casa exato: parcial devolve erro com candidatos (não mexe no ator errado)")
def t_rotulo():
    dt = _carregar()
    r = json.loads(dt.DirectorTools.bone_world_positions("PC_0"))
    assert r["ok"] is False and r["erro"] == "ator_nao_encontrado" and "PC_00" in r["candidatos"], r
    r2 = json.loads(dt.DirectorTools.bone_world_positions("Porta"))
    assert r2 == {"erro": "sem_esqueleto", "ok": False}, r2


@caso("restauração sem nada ativo é idempotente; foto sem setup recusa")
def t_restaura():
    dt = _carregar()
    assert json.loads(dt.DirectorTools.capture_isolated_restore())["motivo"] == "nada_ativo"
    assert json.loads(dt.DirectorTools.capture_isolated_restore())["motivo"] == "nada_ativo"
    assert json.loads(dt.DirectorTools.capture_isolated_shot("x", "y.png"))["erro"] == "sem_rig"
    assert json.loads(dt.DirectorTools.capture_isolated_restore())["ok"] is True


def rodar(testes, rotulo):
    ok = 0
    for t in testes:
        try:
            t()
            ok += 1
            print("OK   ", t.nome)
        except Exception as e:  # noqa: BLE001
            print("FALHA", t.nome, "|", type(e).__name__ + ":", e)
    print(f"{rotulo}: {ok}/{len(testes)}")
    return bool(testes) and ok == len(testes)  # 0/0 é falha, não sucesso


if __name__ == "__main__":
    sys.exit(0 if rodar([t_carrega, t_contrato, t_inventario, t_rotulo, t_restaura], "v003-bloco1") else 1)
