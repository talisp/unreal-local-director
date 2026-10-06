# Inventário: do MCP do Unreal às macros do Hermes

*2026-10-05.*

**Fontes:**
- `work/inventario_mcp.json`: 29 toolsets e 593 ferramentas, lidos do editor;
- `work/baseline.json`: uso e erros do Hermes, 859 chamadas;
- as receitas R-xx do `OPERACAO_UNREAL.md`;
- as FALHA-xx.

## Onde o Hermes mais erra hoje (baseline)

| Ferramenta | Chamadas | Erro | Causa principal | Macro que elimina |
|---|---|---|---|---|
| `execute_tool_script` (scripts escritos na hora) | 503 | 18,9% | ferramenta inexistente, parâmetro obrigatório faltando, `run()` sem dict, propriedade chutada | todas: os scripts passam a ser fixos e testados dentro das macros |
| `get_properties` | 25 | 36% | nome de propriedade chutado (`ActorLabel`, PascalCase) | `inspecionar_cena`, `medir_personagem` (nomes reais em `work/propriedades.json`) |
| `find_actors` | 24 | 12,5% | faltou `tag` ou `collision_channels` | `inspecionar_cena` |
| `load_level` | 10 | 20% | level sujo ou recém-duplicado | proibido trocar de level com o LAB sujo (política, regra 10) |
| `call_tool` mal embrulhado | 6 | 83% | o meta-tool dentro do meta-tool | some: o Hermes não vê mais o MCP |

Dentro dos scripts, as mais chamadas são:
- `get_actor_bounds` (244), `get_properties` (196), `set_properties` (176);
- `write_file` (123), `CaptureViewport` (120), `trace_world` (101);
- `SetCameraTransform` (84), `find_actors` (75), `get_label` (72).

Ou seja: **medir personagem, ler/escrever propriedade e capturar** são o grosso do trabalho.

## Receitas → macros

| Receita / falha | Tarefa (uma frase) | Atômicas usadas | Medida que prova | Dá pelo MCP oficial? |
|---|---|---|---|---|
| — (auditoria) | ver o que há na cena | `find_actors`, `get_label`, `get_actor_transform`, `get_actor_bounds`, `get_properties` | — | sim |
| R-13, R-16, FALHA-15 | medir um personagem | `get_actor_bounds`, `trace_world`, `get_properties` | pose pela SILHUETA de uma cópia no estúdio (bounds NÃO valem: FALHA-21); pés no piso real; distância entre bases | sim (capturas + traces; **osso por quadro, não**) |
| R-05, skill de captura | foto de prova | `SetCameraTransform`, `WorldPosToScreenCoords`, `trace_world`, `CaptureViewport`, `write_file` | alvo dentro do quadro, cobertura ≥ 12%, sem oclusão | sim |
| `FONTES.md` (biblioteca) | achar um clipe por texto | nenhuma (CSV local) | — | — (local) |
| `FONTES.md` (prévias) | ver o clipe antes de importar | nenhuma (ffmpeg local) | 3 quadros extraídos | — (local) |
| R-13 passo 1, FALHA de 05/10 | importar um clipe | `find_assets`, `import_file` (de `animation_motion_ybot/`) | asset `..._Anim_...` existe | sim |
| R-13, R-16, FALHA-15, raiz −100 cm | aplicar um clipe num boneco sem mexer na posição | `get_properties`, `set_properties` (`animationMode`, `animationData`, `bUseRefPoseOnInitAnim`, `relativeLocation`), `get_actor_bounds` | ator inalterado; silhueta de pé; pés no piso (medidos de novo após ajuste) | sim |
| R-13, R-16, R-23 | posicionar personagem num assento ou numa parede | `set_properties` (componente), `trace_world`, `get_actor_bounds` | costas a 35–40 cm da parede; quadril no assento | sim |
| R-22 | porta com dobradiça | `set_actor_transform`, `get_actor_bounds` | gira pelo pivô sem atravessar a parede | sim |
| R-24 | importar asset do Fab | `import_file` (StaticMesh), `find_assets` | asset existe, escala humana | sim |
| R-21, FALHA-19 | montar trecho no Sequencer | `SequencerTools.*` | corpo de pé no fim, sem salto | **bloqueado** (FALHA-19) |
| E7 (fila) | encadear clipes sem salto | Sequencer + medir o Hips por quadro | erro na fronteira ≤ 2 cm | **não**: o MCP não amostra osso no level. Precisa de ferramenta Python dentro do editor (reinício) |

## O que o MCP oficial não cobre (para decisão futura)
1. **Pose de osso num quadro, no level.** Precisaria de ferramenta Python própria dentro do editor (ToolsetRegistry; carrega com o editor reiniciado).
2. **Sequencer avaliando no editor** (FALHA-19, aberta).
3. **Trocar o modo de visão do viewport** (Lit/Unlit): não existe ferramenta.
4. **Descartar alterações ao trocar de level:** `load_level` não tem opção de descartar.
