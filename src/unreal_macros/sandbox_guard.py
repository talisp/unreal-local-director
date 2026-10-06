"""GUARDA DO SANDBOX — NÃO EDITAR (o Claude e o Talis auditam este arquivo pelo git).

Toda chamada ao Unreal feita pelo sandbox passa por `checar`. Leitura passa; escrita só em:
- atores de teste (rótulo TESTE_* ou SANDBOX_*) na zona do sandbox (x >= 15000);
- assets em /Game/_AnimLab/Sandbox/ (e importar clipes em /Game/_AnimLab/Mixamo, sem sobrescrever);
Nunca: salvar fora do Sandbox, apagar/renomear assets, trocar/salvar level, scripts no editor, Play, mexer em malha/esqueleto.
"""

LEITURA = ("get_", "find_", "list_", "describe", "exists", "is_", "trace_world", "search_", "Get", "Is",
           "WorldPosToScreenCoords", "ScreenCoordsToWorld", "CaptureViewport", "CaptureEditorImage")
LIVRES = {"SetCameraTransform", "SelectActors"}  # só mexem na câmera/seleção do editor
PASTA_SANDBOX = "/Game/_AnimLab/Sandbox/"
PASTAS_IMPORT = ("/Game/_AnimLab/Mixamo", "/Game/_AnimLab/Sandbox")
PREFIXOS = ("TESTE_", "SANDBOX_")
X_MIN = 15000.0

_rotulos = {}


class GuardaRecusou(RuntimeError):
    pass


def _rotulo(cliente, ator_ref: str) -> str:
    if ator_ref not in _rotulos:
        _rotulos[ator_ref] = str(cliente._call_cru("editor_toolset.toolsets.actor.ActorTools", "get_label",
                                                   actor={"refPath": ator_ref}))
    return _rotulos[ator_ref]


def _ator_de(ref: str) -> str | None:
    """'/Game/..LAB:PersistentLevel.Ator_3.Comp0' -> '/Game/..LAB:PersistentLevel.Ator_3' (None se não é ator de level)."""
    if ":PersistentLevel." not in ref:
        return None
    base, resto = ref.split(":PersistentLevel.", 1)
    return f"{base}:PersistentLevel.{resto.split('.')[0]}"


def _exigir_teste(cliente, ref: str, tool: str):
    ator = _ator_de(ref)
    if ator is None:
        raise GuardaRecusou(f"{tool}: alvo não é ator de level ({ref})")
    rot = _rotulo(cliente, ator)
    if not rot.startswith(PREFIXOS):
        raise GuardaRecusou(f"{tool}: '{rot}' não é ator de teste (TESTE_/SANDBOX_); o sandbox não mexe na cena")


def _ref(v):
    return v.get("refPath") if isinstance(v, dict) else v


def checar(cliente, toolset: str, tool: str, args: dict):
    if tool.startswith(LEITURA) or tool in LIVRES:
        return
    if tool in ("add_to_scene_from_asset", "add_to_scene_from_class"):
        x = ((args.get("xform") or {}).get("location") or {}).get("x", 0)
        if x < X_MIN:
            raise GuardaRecusou(f"{tool}: spawn em x={x} fora da zona do sandbox (x >= {X_MIN})")
        return
    if tool == "set_label":
        if not str(args.get("label", "")).startswith(PREFIXOS):
            raise GuardaRecusou("set_label: rótulo tem de começar com TESTE_ ou SANDBOX_")
        _rotulos.pop(_ref(args.get("actor")), None)
        return
    if tool in ("remove_from_scene", "set_actor_transform"):
        _exigir_teste(cliente, _ref(args.get("actor")), tool)
        return
    if tool == "set_properties":
        ref = _ref(args.get("instance")) or ""
        if ref.startswith(PASTA_SANDBOX):
            return
        _exigir_teste(cliente, ref, tool)
        return
    if tool == "import_file":
        if not str(args.get("folder_path", "")).startswith(PASTAS_IMPORT):
            raise GuardaRecusou("import_file: só em /Game/_AnimLab/Mixamo ou /Game/_AnimLab/Sandbox")
        return
    if tool in ("create_material", "create", "create_function", "create_parameter_collection"):
        if not str(args.get("folder_path", "")).startswith(PASTA_SANDBOX):
            raise GuardaRecusou(f"{tool}: só em {PASTA_SANDBOX}")
        return
    if tool in ("add_expression", "connect_to_output", "recompile", "delete_expression", "set_scalar_parameter",
                "set_vector_parameter", "layout_expressions"):
        alvo = _ref(args.get("material_or_function") or args.get("expression") or args.get("instance")) or ""
        if not alvo.startswith(PASTA_SANDBOX):
            raise GuardaRecusou(f"{tool}: só em materiais de {PASTA_SANDBOX}")
        return
    if tool == "save_assets":
        ruins = [p for p in args.get("asset_paths", []) if not str(p).startswith(PASTA_SANDBOX)]
        if ruins:
            raise GuardaRecusou(f"save_assets: só salva em {PASTA_SANDBOX} (recusado: {ruins})")
        return
    raise GuardaRecusou(f"{toolset.split('.')[-1]}.{tool}: escrita fora da lista permitida do sandbox")
