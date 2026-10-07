"""O editor roda este arquivo ao abrir, porque a pasta está no UE_PYTHONPATH. Registra o DirectorTools no MCP oficial.
Falha aqui nunca derruba o editor: só registra no log. Rodar de novo (recarga manual) desregistra a versão anterior
antes: recarregar sem isso deixa no catálogo uma classe velha inválida ("Invalid Toolset Class", 06/10)."""
import sys

import unreal

try:
    anterior = sys.modules.get("director_tools")
    if anterior is not None and hasattr(anterior, "_registration"):
        anterior._registration.unregister()
        for m in [m for m in sys.modules if m.startswith("director_tools")]:
            del sys.modules[m]
    from director_tools import _registration

    if _registration.register():
        unreal.log("DirectorTools registrado no ToolsetRegistry")
    else:
        unreal.log_warning("DirectorTools: ToolsetRegistry indisponível (plugin desligado?)")
except Exception as e:  # noqa: BLE001
    unreal.log_error(f"DirectorTools não carregou: {e}")
