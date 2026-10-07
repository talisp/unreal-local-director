# Bancada Hermes v0.0.3 — resumo (06/10, 22:03 → 23:35)

## Placar (27 pedidos: P01–P20, V01–V07)

| Resultado | Contagem | Pedidos |
|---|---|---|
| **Atendido** (feito, com gates e evidência, restaurado) | **9** | P01, P02, P03, P04, P05, P06, P07, P15 + (P06-EXEC substitui o piloto) |
| **Recusado com o motivo certo** | **17** | P08–P13, P16–P20, V01–V07 |
| **Falhou** (tentei, gate/barreira física) | **1** | P14 (foto frontal — parapeito bloqueia) |
| **Emperrei** | **0** | — |

- Conferido por script sobre `pedidos.jsonl` (30 linhas = 27 pedidos + 1 piloto P06 + 2 checkpoints): 8 "atendido" + 1 "atendido_parcial_piloto" (P06, depois executado completo) = 9 únicos atendidos; 18 linhas recusado_certo menos o P06 piloto não-contado = 17 pedidos únicos; bate com a minha contagem manual.
- Nenhum pedido precisou de 3º aplicar_clipe; nenhuma falha repetida 2× num mesmo pedido (a do parapeito apareceu 2×, mas em pedidos diferentes — parei no segundo pela regra).
- **Cena terminou exatamente como começou**: `inspecionar_cena` final confere os 8 PC_18–25 com anim/tempo/loop/posição/yaw idênticos ao baseline salvo (`baseline.json`), nível LAB **não salvo**, nenhum ator movido, escotilha `chamada_avancada` nunca usada.

## Os 3 bloqueios que mais custaram tempo

1. **Ausência de bloco de locomoção (andar)** — derruba sozinho 12 dos 17 pedidos recusados (P08, P10, P16–P20 parcial, V02–V05, V07 via cadeiras). Custou o tempo de análise/planejamento de praticamente toda a Fase 2.
2. **Câmera frontal impossível no mezanino** — o parapeito oclui a vista frontal de qualquer ator da laje (gate `sem_oclusao_cenario` FAIL 2×: P01 e P14; visão confirmou os balaústres sobre as pernas na foto). Custo: 2 capturas perdidas + contornei com lateral; faltou uma opção de câmera elevada.
3. **Custo do `plateia_em_loop`** — 254 s para 1 ator na 1ª vez; no lote de 8 (P06) foram 1.276 s numa chamada (ainda assim 160 s/ator). Foi a maior fatia do relógio da Fase 1 (~26 min só de plateia), e me levou a registrar P06 primeiro como piloto antes da execução completa.

Também lento, mas sem falha: o falso-FAIL do `deriva_xy` em gestos (Talking_2 reprova 19,6; Talking_4 no PC_24 reprova 18,2) — já mapeado como FALHA-26; o teste de 2 candidatos salvou os dois casos.

## Lacunas mais pedidas (dos 18 planos de planos.jsonl)

1. **virar_para / olhar_para (girar yaw até alvo)** — 9 planos (P08, P10, P11, P12, P13, P16, V02, V03, V05). É o pré-requisito silencioso do `andar`: como o bloco anda "para onde o ator olha", quase todo pedido de locomoção morre antes de andar. Candidatos na biblioteca são fracos (Turn_180 só 180°, Holding_Turn_Left só esquerda); a solução pode ser yaw calculado no componente (R-23), não clipe.
2. **sentar(ancora)** — 6 planos (P09, P17, V05, V06-derivados, V07). Clipes existem (`Stand_To_Sit`, `Sitting_4`, `SittingIdle`); o que falta é o bloco cravar o quadril no SeatAnchor e um gate que distinga sentado de agachado.
3. **pegar_objeto / props** — 5 planos (P18, V06, V07, P20, e P14/V03 tangenciam sem prop). Biblioteca: `Pick_Fruit` (reach limpo), `Hiding_Grab` (segurar); attach no socket da mão não existe no Unreal.
4. **sincronizar atores (esperar_até)** — 3 planos (V04, V07, P19). É o teste canônico do "deixa Afonso entrar".
5. **abrir_porta com sentido/dobradiça reais** — 3 planos (P11, V03, V04): a DOOR-SUL abre para dentro; o bloco atual (Open_Door_Outwards, dobradiça esquerda) provavelmente RECUSA essa porta — correto pelo spec, mas deixa a sala sem nenhuma porta que o bloco aceite.
6. Menores: `subir/descer_nivel` (P10, P17, V01-adjacente), `andar_por_caminho` (P17, V02-curridor), `beber` (V07 — não há gesto de beber na biblioteca: busca "drinking" = zero), `spawn_props` (P20).

## Onde fiquei em dúvida sobre a intenção

- **"o homem de azul" (P01)**: ninguém é azul — todos manequins; tratei como faz-de-conta e fixei PC_18 (critério declarado: grupo leste mais próximo da entrada).
- **"olha para o rei" (P12)**: quase todos os do mezanino JÁ olham para o rei pela regra de visão de 05/10 — a resposta honesta ("ele já está nessa direção") é diferente da ação pedida; registrei as duas camadas.
- **"a porta" / "a janela"** (P08, P11, P13, P16, V02): sem qual delas; fixei sempre DOOR-SUL (única nomeada da sala) e a janela mais próxima do ator, com a suposição gravada no registro.
- **"acena" cumprimenta × tchau × chamada** (variações de P01/P16): o mesmo Standing_Greeting cobre, mas "avisando que tô aqui" pedia aceno voltado para dentro — anotei a direção como dúvida de plano.
- **P13 "se vira para a janela"**: escolhi primeiro a janela errada (oeste, quando o PC_19 está do lado leste); corrigido no próprio plano, marcado na linha "duvidas".
- **"pracinha" (P20)**: não é movimento e contraria "nada salvar" — recusei em vez de improvisar cena nova.

## Arquivos
- `<repo>\work\bancada_hermes\v003\pedidos.jsonl` (30 linhas, JSON válido)
- `...\planos.jsonl` (18 planos) · `...\variacoes.jsonl` (21 versões) · `...\baseline.json`
- Evidências em `<evidence dir>\`: v003 P01 acena lateral, P02 conversando, P03 aponta, P04 ombros, P05 palmas, P06 plateia conversa, P07 sim cabeca, P14 foto frente (esta com o parapeito provando o bloqueio)
