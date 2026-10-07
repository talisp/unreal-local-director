# Mapa de lacunas: escada vertical V01–V07 (v0.0.3 Bloco 2, 06/10)

**Como foi feito:** pelo mapa de capacidades (`capacidades.json`) e pelo índice da biblioteca de clipes (2.317 clipes), via `direcao.atendibilidade`. Ainda não foi executado pelo Hermes: ele está em outro perfil, e o resultado seria o mesmo, porque o Director não tem ferramenta para nenhuma das capacidades que faltam.

| Pedido | Situação | Capacidades que faltam |
|---|---|---|
| V01 Marcos se levanta | não atendível | encadear_clipes, levantar |
| V02 … e vai até a porta | não atendível | encadear_clipes, ir_ate_ponto, levantar, virar_para |
| V03 … vai até a porta e a abre | não atendível | encadear_clipes, ir_ate_ponto, porta, virar_para |
| V04 … deixa Afonso entrar | não atendível | coordenar_dois, esperar_condicao, ir_ate_ponto, porta |
| V05 … vão até as cadeiras e se sentam | não atendível | andar_junto, coordenar_dois, ir_ate_ponto, sentar |
| V06 … pegam as xícaras | não atendível | coordenar_dois, pegar_objeto |
| V07 … se sentam e tomam chá | não atendível | coordenar_dois, pegar_objeto, sentar, usar_objeto |

## A lacuna NÃO é animação
A biblioteca já tem os clipes da escada inteira:

| Ação | Clipes |
|---|---|
| levantar / sentar | `Sit_To_Stand`, `Stand_To_Sit`, `Sitting_Idle` (5) |
| andar | `Start_Walking`, `Stop_Walking`, `Walking` (104 de caminhada) |
| virar | 149 de giro |
| porta | `Opening_Door_Inwards`, `Open_Door_Outwards` |
| pegar | `Pick_Up_Item`, `Picking_Up_Object` |
| beber | `Sitting_Drinking`, `Drinking` |
| receber | `Standing_Greeting` |

## O que falta (mecanismos, não clipes)
1. **`encadear_clipes`:** uma sequência A→B→C no tempo. Hoje o `aplicar_clipe` só põe UM clipe em loop.
2. **`ir_ate_ponto` / `virar_para`:** deslocar e orientar o ator. Pela política (regra 7) as macros não movem nem giram atores.
3. **`porta`:** uma folha que gira sincronizada com o gesto (pivô + trajetória, ou física).
4. **`pegar_objeto` / `usar_objeto`:** a xícara presa ao socket da mão a partir de um instante do clipe.
5. **`coordenar_dois` / `esperar_condicao`:** duas linhas do tempo, e uma que espera o estado da outra.

**Consequência (regra arquitetural):**
- **Pedidos bloqueados:** V01–V03.
- **Capacidades:** `encadear_clipes` + `ir_ate_ponto`.
- **Evidência:** o boneco anda ~3 m até um marcador com `Start_Walking`→`Walking`→`Stop_Walking` e para nele. Isso é medido por posição e ossos, sem deslizar os pés e sem atravessar nada.

Esse é exatamente o experimento **Sequencer × Play** do Bloco 2, que vem a seguir.

## Resultado do experimento A (Sequencer), 06/10
Bloco pronto `andar`: `Start_Walking` → `Walking` ×2 → `Stop_Walking`, numa Level Sequence criada pelo DirectorTools (`seq_chain_clips`). Script: `tools/bloco2_seq.py`. Resultados: `docs/v003_resultados/andar_sequencer.json`.

**Medidas:**
- **Avanço do quadril:** medido 644 cm, previsto 643 cm.
- **Saltos nas trocas:** quadril 5,0 / 3,0 / 6,6 cm (≈ 1 quadro de caminhada); dedos 21 / 13 / 11 cm.
- **Vídeo:** 84 quadros de captura isolada → MP4.
- **Limpeza:** a sequência foi apagada e a cena limpa.

**Achados do caminho:**
- **Clipes Mixamo andam pelo quadril**, não pela raiz: ~117 cm por ciclo de `Walking`. O encaixe reposiciona o ator a cada troca pelo avanço do clipe, extrapolado ao último quadro.
- **Mover o cursor pelo Python não reavalia a pose.** É preciso `SequencerTools.set_playhead_frame` + `force_evaluate` (field notes), e ler os ossos em outra chamada.
- **A direção de caminhada é a dos pés** (dedo − tornozelo), não dedo − quadril.
- **O enum certo no 5.8 é `unreal.MovieSceneTimeUnit`.**
- **`duracao_clipe` do Director superestima em 1 quadro** (dívida).

**Decisão Sequencer × Play:** o Sequencer **atende** `encadear_clipes` + `ir_ate_ponto` em linha reta e já sai como vídeo. Fica adotado como caminho principal (hipóteses A/C). O Play fica para quando um pedido exigir física (V06/V07: xícara; porta empurrada).

**Próximos refinamentos do bloco:**
- **Dedos saltando 21 cm na 1ª troca:** fazer uma pequena sobreposição com ease (em ticks, segundo as field notes) entre seções.
- **Distância arbitrária:** cortar o último ciclo ou ajustar o `play rate`, em vez de só um número inteiro de ciclos.
- **Virar até o alvo.**
- **Câmera que acompanha:** a captura atual é fixa e larga.

## V01 e V02 com movimentos prontos (06/10, noite)
**"Fila de movimentos prontos"** (decisão do Talis): o LLM escolhe e encaixa receitas verificadas (`src/unreal_macros/blocos.py`: `andar(distância)`, `levantar()`, `compor(...)`), que o DirectorTools monta no Sequencer (`seq_build`). Os números das receitas vêm de `clip_info`, medidos no clipe. Script: `tools/bloco2_v.py`.

| Pedido | Resultado | Medidas |
|---|---|---|
| V01 "Marcos se levanta" | **5/5** | começa sentado no banco; pés nunca dentro do banco; termina de pé (quadril 94 cm); dedos no chão; 54 cm à frente do banco |
| V02 "… e vai até a porta" | **4/4** | levantar → andar com salto de 2,2 cm; nunca atravessa a porta; para a 54 cm dela (alvo 60) |

Vídeos com câmera que acompanha o quadril e com banco, porta e piso visíveis: `work/bloco2/V01_levantar.mp4`, `work/bloco2/V02_levantar_ir_porta.mp4`.

**Honestidade sobre o V01:** o banco foi posto **a partir da pose** (10 cm abaixo do quadril sentado), então "quadril 10 cm acima do assento" é verdade por construção. O pedido real, um banco ou cadeira que já existe na cena, exige o inverso: posicionar o ator para o quadril cair no assento. Isso é o próximo passo de `levantar`/`sentar`.

**Limites atuais:**
- caminhada só em linha reta, na direção em que o ator já olha (falta `virar_para`);
- distância quantizada pelo ciclo (±75 cm no pior caso; aqui o erro foi de 6 cm);
- iluminação escura na captura isolada (céu desligado);
- `Stop_Walking` termina com um gesto de braço.

## V03 "Marcos vai até a porta e a abre" (06/10, noite): 4/4 dentro da pré-condição
**Receita:**
- `andar` até o alcance da mão; o alcance (70 cm) é medido no clipe `Open_Door_Outwards`;
- depois o próprio clipe: empurrar e passar.

**Porta empurrada pelo corpo** (`blocos.angulos_porta`):
- a cada quadro, a folha abre o mínimo para nenhum dos 15 ossos atravessá-la, e nunca volta;
- as chaves vão para a mesma sequência (`seq_key_transform`);
- nada da porta é animado à mão.

| Teste | Vão 100, dobr. direita | Vão 120, direita | Vão 120, esquerda | **Vão 150, esquerda** |
|---|---|---|---|---|
| porta abre ≥ 60° | 67° | 72° | 86° | **77°** |
| começa pela mão | mão direita | mão direita | mão direita | **mão direita** |
| passa pelo vão | sim | sim | sim | **sim** |
| não atravessa a parede | braço esq. no batente | braço esq. no batente | 15 cm no batente | **nenhum osso** |

**Pré-condição medida e codificada** (`blocos.PRECONDICOES`, `abrir_porta()` recusa fora dela): o clipe do Mixamo exige **vão ≥ 150 cm e dobradiça à esquerda** de quem empurra. Ele empurra com a mão direita e segura com a esquerda, com o braço aberto.

**Lacuna aberta:** porta comum (80–90 cm) ou com a dobradiça à direita exige outro clipe (há `Opening_Door_Inwards` para puxar), retarget/ajuste do braço, ou uma porta de cena dupla.
