# Plano v0.0.3: VERA dentro do Director, com a engenharia do unreal-harness

Rascunho de 06/10/2026, para debate e para a auditoria do Astra. Nada daqui está implementado.

## Decisão
1. **Incorporar ao Director** tudo do VERA que sirva ao objetivo: um diretor autônomo que mede, prova, percebe que emperrou e gera vídeo de referência. O código entra adaptado, com crédito.
2. **Manter o VERA como ferramenta externa**, sem modificação, para uso interativo do Talis com o Strata/Qwen. Ele roda numa **cópia** do projeto, nunca no Florentia enquanto o Hermes trabalha.
3. **O unreal-harness entra como fonte de engenharia.** É dele a moldura que torna as peças do VERA seguras sem um humano aprovando cada passo.

Commits fixados na avaliação:

| Projeto | Commit | Data | Uso |
|---|---|---|---|
| VERA | `8eeb1e7` | 2026-08-10 | código e ideias (MIT) |
| unreal-harness | `09a6bba` | 2026-08-01 | código Python de testes e ideias (MIT) |
| Aethyr | `96bd116` | 2026-10-06 | só ideias; a licença dele exige crédito se usarmos código |
| UnrealCV | `67d466a` | 2026-09-04 | reserva (exige compilar C++) |

---

## Pipeline

### F0. Pré-requisito: fechar a v0.0.2
O que falta do Bloco 5:
- `testes_bloco5` e suíte offline;
- contrato e workflow no Unreal;
- paridade;
- pacote de auditoria;
- auditoria do Astra.

**Porquê:** não se empilha mudança sobre código não auditado.

### F1. Base legal (antes de copiar uma linha)
- `third_party/VERA/LICENSE` e `third_party/unreal-harness/LICENSE`, cópias exatas.
- `THIRD_PARTY_NOTICES.md` com nome, autor, licença, commit fixado e lista de arquivos adaptados.
- Cabeçalho em cada arquivo adaptado: `# Adaptado de VERA (c) 2026 EazyLabs / maVERAick — MIT — commit 8eeb1e7: <arquivo original>`.
- Seção "Créditos" no README público. Ideias sem código copiado (Aethyr, harness) entram como "inspirado em".
- `exportar_publico.py` passa a exigir os avisos no pacote público. Se faltarem, falha.

### F2. Fundação de segurança (vem do harness e do Aethyr; obrigatória antes das peças do VERA que mudam a cena)
O VERA protege as ações destrutivas pedindo confirmação ao humano. No laço autônomo não há humano, então isso precisa virar regra no servidor:
1. **Portões em ordem fixa**, antes de qualquer macro que mude algo:
   - editor pronto;
   - sem janela modal;
   - sem Play;
   - sem PAUSA;
   - trava minha.

   A recusa usa um código da taxonomia fechada.
2. **`dry_run` em toda macro que muda a cena.** Ela devolve o que mudaria (atores, propriedades, assets) sem aplicar. Macro que não sabe fazer prévia recusa o `dry_run`; nunca aplica calada.
3. **Contrato de mutação:**
   - cada macro declara o que toca;
   - o Director fotografa esse estado antes;
   - na falha ou no fim do experimento, restaura (generaliza o padrão `setup → pose → capture → restore` do VERA);
   - antes de qualquer `save_asset`, entra num anel com as 5 últimas cópias (ideia do Aethyr).
4. **Modo só leitura no servidor.** Ele esconde e recusa toda ferramenta que escreve (perfil do Hermes auditor/diagnóstico).
5. **Resultado grande vira resumo + id.** O resto se lê por partes (`ler_resultado`).
6. **Catálogo progressivo.** O Hermes vê um núcleo de cerca de 8 ferramentas mais `catalogo_buscar` / `catalogo_descrever` / `catalogo_chamar`. É o que permite receber as ferramentas do VERA sem inflar o contexto do Qwen.

### F3. Percepção, somente leitura, primeiro (risco baixo)
O ganho é grande e nada é destruído:
- **Captura isolada (show-only list)** como novo motor de medida da silhueta, no lugar do estúdio/"universo paralelo".
- **Ossos no mundo** como segunda medida de pés e pernas.
- **Diagnóstico de animabilidade** (esqueleto e clipes compatíveis).
- **Inventário da cena.**
- **Log do editor.**

A captura isolada só substitui o estúdio depois de vencer o estúdio v2 em experimento com dados reais (veja os critérios abaixo).

### F4. Ações (com portões, `dry_run` e restauração)
- **Aplicar animação:** a escolha de um clipe compatível com o esqueleto vai para `aplicar_clipe`.
- **Retarget:** IK Rig, Retargeter e retarget em lote viram a macro nova `ensinar_clipe`, que traz animações de outros esqueletos para o YBot.
  - Os assets vão sempre para `/Game/_AnimLab/Retarget/`.
  - Nunca sobrescreve.
  - Nunca toca SK_YBot nem a sala de audiência.
- **Clima de cena:** `set_vibe` / `clear_vibe` viram `clima_da_cena` para os vídeos de referência. Os atores são marcados e o efeito é reversível.
- **Desfazer** a última transação, como apoio da restauração e não como substituto.

### F5. Transporte reserva
A ponte do VERA é um socket que roda o código no thread principal via slate tick. Ela vira **reserva** da porta 8001, nunca o padrão:
- só é usada depois de uma falha medida da 8001;
- um teste de paridade roda a mesma macro pelos dois caminhos e compara.

### F6. Futuro: construir lugares
Ficam guardados para "crie uma praça", junto com o 3d-asset-server:
- **PCG Forge:** espalhar objetos numa área.
- **Blueprint Forge:** criar Blueprints de ator.

### F7. VERA externo
Instalar o VERA sem modificação numa **cópia** do projeto, com o Strata como provedor local.
- **Regra:** o VERA não conhece a nossa trava. Ou fica num editor separado, ou exige o Hermes em PAUSA.
- **Uso:** trabalho interativo do Talis. O que funcionar bem lá vira candidato a macro no Director.

### F8. Esteira de entrada de cada peça
Toda peça percorre os mesmos passos, sem atalho:
1. **Ler e fixar** o arquivo e o commit de origem.
2. **Adaptar ao envelope do Director:**
   - relatório com `medidas`, `evidencias`, `bloqueio`, `espera`;
   - erro traduzido para a taxonomia fechada.
3. **Portões e `dry_run`**, para peças que mudam algo.
4. **Teste offline** com saídas falsas do editor (padrão `fakes` do VERA mais as nossas fixtures).
5. **Teste no Unreal real**, com marcação `@cobre`. Um oráculo de cobertura reprova macro sem teste real.
6. **Paridade** sandbox × v0.0.3.
7. **Experimento do Hermes** no sandbox com pedidos do banco `pedidos_v0`. A métrica é Pedidos Atendidos, antes e depois.
8. **Pacote compacto** para o Astra.
9. **Produção**, só depois da auditoria. **Publicação no GitHub**, só com permissão do Talis.

---

## Tudo do VERA, peça por peça

### Entra no Director
| # | Peça do VERA | Origem | Vira no Director | Fase |
|---|---|---|---|---|
| 1 | Captura isolada de um ator (`SceneCapture2D` + show-only list + render target) | `vera/agent/tools/_capture_scripts.py`, `capture_actor.py` | motor novo de `medir_personagem` e `capturar_evidencia`; aposenta o estúdio se vencer | F3 |
| 2 | `ALWAYS_TICK_POSE_AND_REFRESH_BONES` (pose avaliada fora do viewport) | `_capture_scripts.py` | padrão em toda medida de pose, restaurado depois | F3 |
| 3 | Regra "pose numa chamada, captura em outra" | `_capture_scripts.py` (`build_pose_script`) | regra escrita do motor de captura; deve explicar e substituir a captura de aquecimento | F3 |
| 4 | `SCS_FINAL_COLOR_LDR` (o base color sai branco no 5.7) | `_capture_scripts.py` | configuração do motor, com teste no 5.8 | F3 |
| 5 | Câmera em órbita (vista em ângulo X sem mexer no ator) | `_POSE_TEMPLATE` | vistas frontal / lateral / 45° de `capturar_evidencia` | F3 |
| 6 | Diagnóstico de animabilidade (tipo, esqueleto, clipes compatíveis) | `_anim_scripts.py` (`_diagnose`), `inspect_actor_animability.py` | parte de `resolver_ator`; responde "por que não anima" antes de tentar | F3 |
| 7 | Busca de ator com candidatos parecidos | `_anim_scripts.py` (`_find_actor`, `_candidates`) | `resolver_ator` devolve sugestões em vez de só "não achei" | F3 |
| 8 | Inventário da cena (contagens, classes, luzes) | `inspect_level.py` | complemento de `inspecionar_cena` | F3 |
| 9 | Leitura do log do editor | `read_editor_log.py` | `ler_log_editor` (só leitura) e fonte para o supervisor | F3 |
| 10 | Escolha de clipe compatível e tocar/parar | `_anim_scripts.py` (`_pick_and_play`, spawn, stop) | reforça `aplicar_clipe` e `restaurar_animacao` | F4 |
| 11 | IK Rig: garantir que existe | `ensure_ik_rig.py`, `_retarget_scripts.py` | parte de `ensinar_clipe` | F4 |
| 12 | IK Retargeter: garantir que existe | `ensure_retargeter.py`, `_retarget_scripts.py` | parte de `ensinar_clipe` | F4 |
| 13 | Retarget em lote (`IKRetargetBatchOperation`) | `retarget_animations.py`, `_retarget_scripts.py` | `ensinar_clipe`: clipes de outros esqueletos para o YBot | F4 |
| 14 | Clima de cena (luz e pós-processo marcados, 5 climas, reversível) | `VERA_Plugins/scene-vibe/` | `clima_da_cena` / `limpar_clima` para os vídeos de referência | F4 |
| 15 | Desfazer última transação | `undo_last_action.py` | apoio da restauração do contrato de mutação | F4 |
| 16 | Ponte por socket no thread principal (slate post-tick) | `UE57/Content/Python/vera_bridge.py`, `vera/tools/ue_conn.py` | transporte reserva da 8001 | F5 |
| 17 | Bootstrap de dependências no Python embutido | `vera_bootstrap.py` | instalação do transporte reserva sem pip manual | F5 |
| 18 | PCG: amostrador de superfície + spawner, ligados | `VERA_Plugins/pcg-forge/` | bloco de construção para "crie uma praça" | F6 |
| 19 | Criar Blueprint de ator pela API de grafo | `VERA_Plugins/blueprint-forge/` | bloco de construção para objetos interativos (porta, xícara) | F6 |
| 20 | Busca de asset por nome no Content | `project-intelligence/tools/find_asset.py` | junto com o catálogo de clipes; depois, com o 3d-asset-server | F6 |
| 21 | Padrões de engenharia: scripts curados com tokens injetados por `json.dumps`, saída JSON compacta de uma linha, estado de sessão em `sys.modules` com restauração idempotente, testes com `fakes` | vários | convenção para macros novas e testes offline | F2–F8 |
| 22 | Formato de plugin (pasta com `tools/` + `SKILL.md` + `plugin.json`) | `vera/agent/plugins.py` | formato das categorias do catálogo progressivo | F2 |

### Não entra (com o motivo)
| Peça | Motivo |
|---|---|
| Laço de agente, cliente multi-provedor, adaptador OpenAI, streaming de `<think>` | O agente é o Hermes; o Director é a camada de ferramentas. |
| Interface de chat (Qt/WebEngine, 1.300 linhas), histórico, reload | Fica no VERA externo (F7). |
| Modos Ask / Auto / Read | Dependem de um humano aprovando; viram os portões, o `dry_run` e o modo só leitura (F2). |
| `run_ue_python` livre | Contradiz a política: já temos `chamada_avancada` com motivo registrado. |
| Local IQ (receitas) | As lições ExpeL do Director já fazem mais; as receitas do repositório são lixo duplicado. |
| Memory | Já temos diário, lições e passagem de sessão. |
| Computer Use (clicar na tela) | Risco alto num laço autônomo; nunca. |
| Source Control | Já temos git com worktree por experimento. |
| Mobile / Performance Doctor | Fora do objetivo. No máximo `profile_level`, um dia, para diagnosticar editor lento. |
| Blackboard | Resto de uma arquitetura antiga do próprio VERA. |
| `epic_proxy` / cliente MCP da Epic | Já temos um cliente da 8001 testado. |

---

## O que o unreal-harness faz pela integração
Sem compilar o plugin dele (é C++ para UE 5.7, com servidor em Bun):

| # | Do harness | Como ajuda a integrar o VERA |
|---|---|---|
| 1 | Catálogo progressivo (`catalog_domains/search/describe/call`) | As ~15 ferramentas novas entram sem inflar o contexto do Qwen. |
| 2 | Portões em ordem fixa (boot → PIE → dry-run) | Substituem o "perguntar ao humano" do VERA nas ferramentas destrutivas. |
| 3 | Envelope único + taxonomia fechada de erros, com teste de paridade | Os erros soltos do VERA (`not_found`, `no_anims`, `not_skeletal`, `anim_not_compatible`) viram tipos do `resolver`; um teste reprova código sem tradução. |
| 4 | Contrato de mutação + "tudo que mexe no editor é limitado e se limpa" | Generaliza o `restore` do VERA para toda macro; o `_cleanup.py` (MIT, Python) mata processos órfãos. |
| 5 | Testes com editor real + oráculo de cobertura `@covers` (MIT, Python) | Nenhuma peça do VERA chega ao Hermes sem teste real. |
| 6 | `capture-pose`: o humano enquadra uma vez, a pose vira arquivo | Junto com a captura do VERA vira a **câmera fixa dos vídeos de referência**, sempre do mesmo ângulo. |
| 7 | `see.py` / `vision_critic.py`: medida numérica de imagem + PNG anotado como prova | Padrão de evidência: número primeiro, imagem anotada para conferir; visão só depois da medida. |
| 8 | Contrato do `video_analyze` (esperado × observado, com tempo e severidade) | Formato para julgar "pedido atendido" num vídeo; o Gemini fica de fora, entra um modelo de visão local quando houver. |
| 9 | Lease em fila (FIFO, TTL, posição na fila) | Estende a nossa trava quando VERA externo, Hermes e Claude disputam o mesmo editor. |
| 10 | Compactação de resultado com handle (`result_read`) | Para listas grandes do VERA (clipes compatíveis, inventário). |
| 11 | Log unificado num só fio do tempo | Log do editor (peça 9) + `eventos.jsonl` + relatórios numa linha do tempo para o supervisor. |
| 12 | Skill `position` + sondas de cinemática | Convenções do UE (eixos, ordem do FRotator, manequim) para a skill do Hermes e a medida por ossos. |
| 13 | Doutrina "nunca jogar para validar" | Regra escrita na skill `resolver-problemas`: se o teste pilota personagem ou câmera, é palpite. |

**Não usar do harness:** o plugin C++, o servidor Bun/TS e as skills de AWS/GameLift, Neo4j, GIMP, ícones e rede.

---

## Critérios de aceite das peças principais
- **Captura isolada (1–5):** substitui o estúdio só se, nos 4 clipes de referência (Talking_2, Waving_2, Hands_Forward, Walking):
  - as medidas ficarem dentro de ±2 cm / ±2 % das do estúdio v2;
  - a repetição tiver |gap| ≤ 2 **sem** captura de aquecimento;
  - houver menos chamadas;
  - nenhum ator sobrar na cena.
- **Ossos (2):** pés e pernas pelos ossos concordam com a silhouette em ≥ 3 dos 4 clipes; onde discordarem, o caso é explicado.
- **`ensinar_clipe` (11–13):**
  - um clipe de outro esqueleto passa nos portões de pose;
  - nenhum asset fora de `/Game/_AnimLab/Retarget/` é salvo;
  - o `dry_run` lista exatamente o que será criado.
- **`clima_da_cena` (14):** aplica e limpa sem deixar ator; a cena volta a ser idêntica pelo inventário antes/depois.
- **Transporte reserva (16):** a mesma macro pelos dois caminhos dá o mesmo relatório; a reserva não é usada sem falha medida da 8001.
- **Hermes (F8.7):** Pedidos Atendidos no banco `pedidos_v0` não piora, e melhora nos pedidos de animação.
