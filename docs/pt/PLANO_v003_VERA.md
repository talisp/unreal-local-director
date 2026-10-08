# Plano v0.0.3 (v2): VERA no Director, guiado por testes verticais

> Documento de **plano** (histórico da v0.0.3). Estado real: [ESTADO_ATUAL.md](ESTADO_ATUAL.md) · decisões: [DECISOES.md](DECISOES.md) · fontes: [FONTES_EXTERNAS.md](FONTES_EXTERNAS.md).

Versão 2 do plano, de 06/10/2026. Junta o plano original do Claude, as revisões do ChatGPT e as correções vindas das field notes do MCP 5.8. Está em execução na branch `v0.0.3`.

## Objetivo
Incorporar ao Director o máximo de engenharia e código útil do VERA, com a atribuição correta, e usar esse salto como base para avançar na execução de **pedidos humanos compostos**.
- **A ordem de incorporação** não vem do inventário do VERA. Vem dos bloqueios observados nos testes verticais de Pedidos Atendidos.
- **Projetos além do VERA** só são estudados e incorporados quando uma lacuna concreta justificar.

## Regra arquitetural
**A partir do Bloco 2, nenhum bloco novo é aberto sem citar três coisas:**
1. qual pedido vertical está bloqueado;
2. qual capacidade está faltando;
3. que evidência vai mostrar que o bloco resolveu a lacuna.

## Economia de cota
- Claude e Astra são gastos onde vêm os saltos grandes: o toolset, o VERA e o primeiro teste vertical.
- A v0.0.2 **não** é terminada isoladamente (Bloco 0).
- O Astra audita **uma vez**, a candidata da v0.0.3 que de fato vai para a produção.

## Posicionamento na publicação da v0.0.3 (pedido do Talis, 06/10)
Quando a v0.0.3 for para o GitHub (não antes), o README e a descrição do repositório mudam de contexto:
- **O Director não é mais "uma ferramenta de IA" para o Unreal.**
- **A função dele:** transformar intenção humana em ações verificadas no Unreal, usando uma LLM local que, sozinha, não teria capacidade de operar o engine de forma confiável.
- **O valor está na camada de verificação:** macros, medidas, portões, trava, detector de emperramento e restauração. O modelo é só a ponte entre o pedido e essa camada.

## Fontes
A tabela de fontes (licença, commit, situação e o que entrou) vive em **[FONTES_EXTERNAS.md](FONTES_EXTERNAS.md)**, a fonte canônica. Este plano guarda o inventário detalhado do VERA e do harness, mais abaixo.

---

## Bloco 0: congelar a v0.0.2, não terminá-la (FEITO em 06/10)
- Suíte offline: 137/137 **não verificado** (07/10: as 10 suítes listadas somam 100, não 137; ver `work/harness_E4/quebra_RESULTADO.md`).
- Estado e dívida de validação estão em `docs/BLOCO5_STATUS.md`; tag `v0.0.2-congelada`.
- A v0.0.2 é "base experimental, validação real incompleta". Trava, PAUSA, supervisor, detector e controlador de experimentos são fundações **não totalmente provadas**: se falharem durante a v0.0.3, viram prioridade imediata.
- **Revalidação:** seletiva quando a v0.0.3 mexer em cada área; integral na auditoria final.
- **Custo aceito:** até a candidata da v0.0.3 ir para a produção, o Hermes segue sem o detector e o supervisor da v0.0.2.

## Bloco 1: a porta técnica para o VERA
**Problema:** o executor de scripts da Epic (`execute_tool_script`) é um sandbox sem `unreal`, `os` nem arquivos, e o código do VERA usa a API `unreal` direto.

**Solução:**
- um **toolset Python dentro do editor** (`DirectorTools`), no formato oficial da Epic (`unreal.ToolsetDefinition` + `toolset_registry.tool_call`), carregado por `init_unreal.py`;
- a pasta é apontada por `UE_PYTHONPATH`, em C:, sem escrever no projeto em Y:;
- tudo continua pela porta 8001 e sob a mesma trava; a ponte socket do VERA fica só como plano B.

**Entregas:**
1. **`DirectorTools`** com:
   - `ping` (prova de Python completo);
   - posição de ossos no mundo, avaliando a pose fora do viewport (`ALWAYS_TICK_POSE_AND_REFRESH_BONES`, restaurado depois);
   - **captura isolada de um ator** (SceneCapture2D + show-only list, adaptada do VERA), com restauração idempotente;
   - inventário completo de atores (sem o corte de 20).
2. **Instalação reversível:**
   - variável `UE_PYTHONPATH` + um reinício do editor, numa janela combinada com o Talis e o Hermes em PAUSA;
   - desinstalar é remover a variável.
3. **Testes das field notes no Unreal real:**
   - `find_actors` corta em 20? (comparar com o inventário completo);
   - o save é comprovado por releitura e disco;
   - `CaptureViewport` respeita a pose? (`cameraLocation`);
   - caminhos resolvidos com `find_assets` antes de scripts;
   - a primeira captura depois de uma mudança traz o quadro anterior?
4. **Base legal:** `third_party/VERA/LICENSE`, `THIRD_PARTY_NOTICES.md` e cabeçalho em cada arquivo adaptado.

**Aceite:**
- `list_toolsets` mostra `DirectorTools` e as 4 ferramentas respondem;
- a captura isolada não deixa ator nem mudança na cena (inventário antes = depois);
- os ossos de pé/perna batem com a silhueta em pelo menos 3 dos 4 clipes de referência, e onde discordam o caso é explicado;
- cada risco das field notes vira teste com resultado registrado.

## Bloco 2: benchmark vertical antes de escolher o resto da arquitetura
**Família V no `pedidos_v0`:**

    V01  Marcos se levanta.
    V02  Marcos se levanta e vai até a porta.
    V03  Marcos vai até a porta e a abre.
    V04  Marcos abre a porta e deixa Afonso entrar.
    V05  Marcos e Afonso vão até as cadeiras e se sentam.
    V06  Marcos e Afonso pegam as xícaras.
    V07  Marcos e Afonso se sentam e tomam chá.

**Rodar com o Director atual**, sabendo que quase tudo vai falhar. O produto é o **mapa de lacunas**:
`pedido → etapa alcançada → capacidade ausente → motivo da falha → mecanismo que provavelmente resolve`.

**Decisão Sequencer × Play, por experimento e não no papel.** Dois experimentos mínimos sobre o mesmo pedido ("andar três metros até um marcador"):
- **A, Sequencer:** trajetória + animação + avaliação + captura.
- **B, Play:** CharacterMovement/nav + animação + chegada + captura.
- **Hipótese C, híbrida (a mais provável):** Sequencer como linha do tempo autoral e resultado final; Play como simulador/verificador quando física ou navegação importam.

Critérios de comparação:
- determinismo e repetibilidade;
- facilidade de verificar o resultado;
- facilidade de encadear ações;
- colisão e física;
- custo em chamadas;
- recuperação após falha;
- geração de vídeo;
- estabilidade com o Hermes.

O que as field notes já avisam:
- **Sequencer:**
  - `create_level_sequence` sobrescreve sem avisar;
  - a seção nasce com faixa 0..0;
  - a duração do ease é em ticks;
  - `set_camera_cut_binding` está quebrado (o contorno é `CameraBindingID` via `set_properties`);
  - `get_actor_transform_at_frame` serve para seguir trajetória;
  - o FK Control Rig exige um passo manual.
- **Play:** classificadores de permissão do cliente bloqueiam `StartPIE`, e `save_assets` falha depois de PIE.

## Blocos 3+: abertos sob demanda (regra arquitetural)

    falha do teste vertical → capacidade faltando → qual fonte já resolve → ler o código
    → adaptar só a peça útil (esteira abaixo) → teste vertical de novo

Mecanismos de segurança que acompanham cada peça que muda a cena (harness/Aethyr):
- portões em ordem fixa: editor pronto, sem janela modal, sem Play, sem PAUSA, trava minha;
- `dry_run` (macro que não sabe fazer prévia recusa);
- contrato de mutação com fotografia do estado e restauração;
- anel de backup com 5 cópias antes de qualquer save;
- modo só leitura;
- resultado grande vira resumo + id;
- catálogo progressivo para não afogar o Qwen.

### Esteira de entrada de cada peça
1. Ler e fixar o arquivo e o commit de origem.
2. Adaptar ao envelope do Director (`medidas`, `evidencias`, `bloqueio`, `espera`) e à taxonomia fechada de erros.
3. Portões e `dry_run`, se a peça muda algo.
4. Teste offline (padrão `fakes` do VERA mais as nossas fixtures).
5. Teste no Unreal real com `@cobre`; o oráculo de cobertura reprova macro sem teste real.
6. **Regressão seletiva** das áreas da v0.0.2 tocadas.
7. Teste vertical de novo; a métrica é Pedidos Atendidos.
8. Fim da v0.0.3: auditoria Astra única da candidata, produção, e GitHub com permissão.

### VERA externo (paralelo, opcional)
- VERA sem modificação numa **cópia** do projeto, com o Strata, para uso interativo do Talis.
- Ele não conhece a nossa trava: editor separado, ou Hermes em PAUSA.

---

## Inventário do VERA (o que está disponível, NÃO a ordem de implementação)

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
