# Código de terceiros

## VERA: Virtual Engine Reasoning Agent
- Origem: https://github.com/ezesubu/VERA, commit `8eeb1e7` (2026-08-10)
- Licença: MIT, (c) 2026 EazyLabs / maVERAick; cópia em `third_party/VERA/LICENSE`
- Adaptado: `editor_python/director_tools/toolset.py`, a partir de `vera/agent/tools/_capture_scripts.py`:
  - captura isolada por SceneCapture2D + show-only list;
  - avaliação da pose fora do viewport;
  - estado de sessão com restauração idempotente.
- Mudanças: casamento de rótulo só exato, com candidatos; ferramentas no formato ToolsetRegistry da Epic; câmera por yaw/pitch/distância; arquivo conferido em disco.

## Ideias (sem código copiado)
- unreal-harness (MIT, Oliver Carrillo): https://github.com/oliver-io/unreal-harness
- Aethyr (Doug Fessler): https://aethyr.gg
- ue58-mcp-field-notes (CC BY 4.0, Pavel Vyny): https://github.com/PavelVyny/ue58-mcp-field-notes. As armadilhas do MCP 5.8 que viraram testes e portões citam esta fonte.
