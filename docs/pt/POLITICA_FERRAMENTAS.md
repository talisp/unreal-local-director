# Política de ferramentas do Hermes no Unreal

*v1, 2026-10-05. Baseada no `TOOL_LAYERING_POLICY.md` do blender-ai-mcp, nas skills oficiais da Epic e nos erros reais do Hermes (baseline: 15% de erro em 859 chamadas). Delegada pelo Talis.*

## Camadas

| Camada | O que é | Quem usa |
|---|---|---|
| **Atômica** | as 593 ferramentas do MCP oficial (`call_tool`, `execute_tool_script` etc.) | só as macros, por dentro |
| **Macro** | uma tarefa que se diz numa frase ("aplicar este clipe neste boneco"), com leitura de volta e medida embutidas | **o Hermes** (camada principal) |
| **Workflow** | um processo limitado que encadeia macros e gates e entrega relatório ("plateia em loop, um por um") | **o Hermes** |
| **Verdade** | medidas e asserções determinísticas (silhueta da cópia no estúdio, traces, propriedades lidas de volta; bounds NÃO valem para pose) | todas as macros |
| **Visão** | segunda opinião sobre uma captura | workflows, depois dos gates numéricos |

## Regras

1. **Superfície pública pequena.** O Hermes vê macros, workflows e a escotilha. Ele não chama ferramentas atômicas nem escreve scripts para o editor.
2. **Escotilha só de leitura.** `chamada_avancada` permite apenas leitura (get/find/list/describe/trace); recusa escrita e scripts e registra tentativa, resultado e erro. Falta de macro vira pedido via `registrar_falha`.
3. **Objetivo primeiro.** Toda macro aceita `contexto = {objetivo, alvo, fase, criterios}` e o devolve no relatório.
4. **Relatório único.** Toda macro devolve `{macro, ok, medidas, evidencias, avisos, bloqueio, chamadas, segundos}`. `ok=false` traz o motivo em `bloqueio`. Nunca "true" sem medida.
5. **Verdade é medida.** Uma macro que muda a cena lê de volta o que mudou e mede o resultado. A visão nunca aprova sozinha; número PASS + imagem FAIL = FAIL. Um NÃO da visão no critério principal não pode ser descartado.
6. **Nunca destruir em silêncio.** Apagar, sobrescrever ou salvar fora de `/Game/_AnimLab/` exige pedido explícito do Talis no contexto. Nunca salvar `SK_YBot`, `SK_YBot_Skeleton` nem a sala de audiência. `save_assets` só com caminhos explícitos.
7. **Preservar o que o Talis arrumou.** Uma macro de animação não move o ator. Só ajusta o componente, e só pelo que mediu (ex.: a compensação da raiz). Ela registra o "antes" no relatório.
8. **Um de cada vez.** Um workflow que muda vários atores para no primeiro FAIL. Nada de lote às cegas.
9. **Um agente por vez no Unreal.** As macros usam a trava `unreal-macros/work/unreal.trava` (uma macro por vez entre processos). Ela não impede outro agente que use o MCP bruto: o MCP bruto fica desligado para o Hermes.
10. **As regras de ferro herdadas (R-xx e FALHA-xx) vivem dentro das macros,** não na memória do modelo. Exemplos: girar o componente, não o ator; `bUseRefPoseOnInitAnim=false`; importar animação de `animation_motion_ybot/`; não reexportar pelo Blender; nunca trocar de level com o LAB sujo.
11. **Uma macro nova só entra para o Hermes** depois de passar 3 de 3 nos casos positivos e de reprovar o controle negativo.
12. **Compatibilidade fica abaixo da macro.** Se o Unreal mudar nomes de propriedade ou de ferramenta, corrige-se a macro; o Hermes não precisa saber.
