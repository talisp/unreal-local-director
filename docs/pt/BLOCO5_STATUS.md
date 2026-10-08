# v0.0.2 — Bloco 5 (validação no Unreal): status ao parar (06/10, ~17:50)

**v0.0.2 CONGELADA em 06/10 (Bloco 0 da v0.0.3)** como "base experimental, validação real incompleta". Ela não será terminada isoladamente: a validação que falta vira dívida, paga por **regressão seletiva** quando a v0.0.3 mexer em cada área, e por inteiro na **auditoria Astra da candidata da v0.0.3**. Não houve auditoria Astra da v0.0.2.

Suíte offline no congelamento: **137/137** **não verificado** (07/10: as 10 suítes listadas somam 100, não 137; ver `work/harness_E4/quebra_RESULTADO.md`). Diário 3, bloco1 8, bloco2 21, caracterização 11, bloco3 16, bloco3b 11, bloco4 8, supervisor 10, sessão 8, bloco5 4. Um ajuste: o cenário de `sv_espera` declarava um prazo de 25 min e era avaliado aos 55 min; depois da regra `corrida_perdida` do bloco 5, isso é corretamente um alarme, então o prazo do cenário passou a 60 min.

Fundações da v0.0.3 ainda **não totalmente provadas**: trava, PAUSA, supervisor, detector e controlador de experimentos. Se uma delas falhar durante a v0.0.3, vira prioridade imediata.

---
(registro original do Bloco 5)

**Conclusão: NÃO PRONTA PARA AUDITORIA** — o bloco foi interrompido a pedido do Talis antes da suíte final.

## Feito (resultados em `work/bloco5/*.json`)
| Seção | Resultado |
|---|---|
| 0 Estado inicial | 5/5 (sem Play, sem TESTE_, produção intacta, versão no relatório) |
| Suíte offline antes do Unreal | 96/96 |
| 1 Paridade de código | 14/16 arquivos idênticos; `macros.py` com funções idênticas (só constantes); `mcp_client` só o gancho da guarda |
| 1 Paridade de execução | OK (178,2 cm; gap −0,5 / −0,1) |
| 2 Teste rápido | 9/9 |
| 3 Deriva pelas pernas | 8/8: Talking_2 5,2 · Waving_2 2,4 · Hands_Forward 2,9 (PASS); Walking FAIL ("saiu da janela"); checagem extra: pernas andam 18 cm nos instantes mensuráveis |
| 3 Captura estável | OFF caminho antigo (111 chamadas, 22,9 s); ON declarado (112, 41,0 s) — fica desligada |
| 4 Trava (processos reais) | 5/5, concorrência: 1 de 6 |
| 4 Experimento real | 8/8 (worktree, código do sandbox, 2/2, ids, recusas reais) |
| 5 Detector com dados reais | 5/5 (repetição → cutucar → lição → progresso → voto +1; espera real não conta) |
| 6 Banco/fila/supervisor | B, C, D, E, F OK após correções; A e fila OK em sessão limpa (6a 3/3) |
| 6 Rotação (cópia dos dados reais) | 5/5 |
| 7 Falhas provocadas | 4/4 após correção |
| 8 Correlação do transporte | OK (resposta de outra requisição ignorada) |

## Bugs achados com dados reais e corrigidos neste bloco
1. Espera por trava escondia o relógio do supervisor por 10 min fixos → agora termina na próxima tentativa.
2. "Emperrado" sumia com tentativa posterior de outra linha → agora = degrau ativo.
3. Macro barrada pela PAUSA contava como tentativa → agora é espera `pausa` (`PausaAtiva`).
4. Ordem incerta no mesmo segundo entre fontes → `quando_ts` (ms) no relatório e eventos com ms.
5. Corrida interrompida ficava como espera eterna → alarme `corrida_perdida` após o prazo declarado.
Testes permanentes: `src/testes_bloco5.py` (4 casos; o 1º teve a expectativa do tipo de alarme corrigida, ainda não re-executado).

## Dívida de validação (paga na v0.0.3, seletivamente)
1. ~~Suíte offline completa depois das correções do bloco 5~~ — feita no congelamento: 137/137.
2. **Contrato + workflow completos no Unreal** com o código final.
3. **Paridade** de novo (o código mudou depois da primeira paridade).
4. Pacote de auditoria compacto (SHAs, diff resumido, resultados) e commit final.

## Achados para a auditoria / entrada em produção
- A trava da v0.0.2 (`v002/work/unreal.trava`) e a do sandbox precisam apontar para a MESMA trava que a produção.
- Hash de arquivos deve ser comparado com quebras de linha normalizadas (CRLF no Windows).
- Commit `2be5a4b` do sandbox de teste contém a sincronização do supervisor com mensagem imprecisa ("corrida longa").
- PID reaproveitado testado com horário forjado (não dá para forçar o SO a reusar PID).
- "Resultado tardio" no transporte não foi reproduzido.

## Ambientes
- v0.0.2: `<repo>` (branch v0.0.2; base Bloco 4 `8dc3438`).
- Sandbox de teste: `<sandbox>-v002` (o sandbox do Hermes não foi tocado).
- Produção: intacta (hashes conferidos); trava da produção LIBERADA ao parar; cena limpa (sem TESTE_).
