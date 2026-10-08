# Changelog

## v0.0.4-wip — a LLM propõe; o programa mede, registra e protege (em construção, 08/10)
Plano: `docs/PLANO_PROXIMA_VERSAO.md` (privado). **Não terminada:** o teste grande no Unreal (cena com variações) está pronto sem o Unreal, mas ainda não rodou ao vivo; falta o fechamento da versão.

- **Bateria de quebra** (`tools/bateria.py`): num worktree do commit, Ruff e basedpyright contra a linha de base (só o que é novo), 16 suítes sem Unreal, propriedades Hypothesis (uma por classe de entrada), conferência da porta 8001, da trava e do `pip freeze`. Último resultado: OK, 16 suítes, 0 avisos novos, ~38 s.
- **Régua e receita** (`src/unreal_macros/fila.py`, `receita.py`): critérios levantar, acenar, andar, parar, trocas e duração; receita validada e com assinatura; ajustes por passo `inicio_q`, `corte_fim_q` (0 a 120 quadros) e `turn_fim_deg` (±180°), fora da régua.
- **Executor único da fila** (`tools/fila_executor.py`): trava, montagem, medida, registro com as condições da medida, limpeza e retomada; prazo contado do início da rodada; filho só com autorização de uso único; cena validada no próprio executor (3 achados do Astra, todos corrigidos com teste).
- **Biblioteca** (`src/unreal_macros/biblioteca.py`, `biblioteca/*.jsonl`): blocos, trocas (138 medidas), fichas e escolhas; a mesma troca custa o mesmo em qualquer receita; consultas expostas no servidor MCP.
- **Trava** criada de forma atômica; blocos recusam zero, negativo, NaN e infinito.
- **As 4 linhas de trabalho**, um comando cada (`tools/director.py`): júnior (ideias conferidas e auditadas, `tools/junior.py`), bateria, teste grande no Unreal (cena em `cenas/fila.md`, variações diferentes de verdade com vídeo, escolha do operador, `tools/linha2.py` + vigia) e Astra (revisão só leitura, resposta conferida, `tools/astra.py`).
- **Painel local** (`tools/painel.py`, `127.0.0.1:8765`) e **rotinas de um clique** (`tools/rotina.py`): botões para rodar as linhas (janela minimizada, sem roubar o foco), histórico ao vivo, gráfico das notas, vídeos, escolha da variação, aprovação de ideias e um resumo curto montado por programa no fim de cada rotina.

## v0.0.3 — VERA no Director, guiado por testes verticais (em construção)
Plano: `docs/PLANO_v003_VERA.md`.

### Bloco 0 — v0.0.2 congelada, não terminada
- A suíte offline passa 137/137 **não verificado** (07/10: as 10 suítes listadas somam 100, não 137; ver `work/harness_E4/quebra_RESULTADO.md`). Hoje: 61 de 110 com o editor fechado; 34/34 nas suítes que rodam sem o Unreal. A dívida de validação real está registrada em `docs/BLOCO5_STATUS.md`. Não houve auditoria Astra da v0.0.2: a auditoria será da candidata da v0.0.3.

### Bloco 1 — porta técnica para o VERA (VALIDADO no Unreal 5.8.3 em 06/10)
- **DirectorTools**, um toolset Python dentro do editor (`editor_python/`), registrado no MCP oficial via `UE_PYTHONPATH` + `init_unreal.py`, sem escrever no projeto. Ferramentas:
  - `ping`;
  - `list_actors` (inventário sem o corte de 20);
  - `set_pose_eval`, `bone_world_positions`, `bone_position_in_clip`;
  - captura isolada adaptada do VERA (`capture_isolated_setup` / `_shot` / `_restore`).
- Créditos: `THIRD_PARTY_NOTICES.md` e `third_party/VERA/LICENSE`. O rascunho antigo `editor_toolset/` sai.
- Testes offline: `src/testes_v003_bloco1.py` 5/5.
- **Unreal real** (`tools/bloco1_unreal.py`; resultados em `docs/v003_resultados/`): ping 1/1, campo 3/3, captura 8/8, ossos 4/4.
  - Instalado via `UE_PYTHONPATH`; carrega sozinho ao abrir o editor.
  - **Captura isolada:** só o ator pedido aparece (vizinho e piso somem); céu, atmosfera e neblina desligados dão fundo preto e uma silhueta limpa; a cena fica idêntica antes e depois.
  - **Ossos:** os pés e o quadril são lidos nos 4 clipes de referência. Talking_2 e Hands_Forward concordam com a silhueta (dedos a ~3 cm do piso). Walking também (um pé no ar; a silhueta reprova pela janela). Waving_2, neste instante, mostra os dedos a ~9 cm, contra ~3 cm numa leitura anterior: falta amostrar ao longo do clipe.
- **Field notes conferidas no 5.8.3:**
  - `find_actors` NÃO corta em 20 aqui (93 atores);
  - `CaptureViewport` respeita a pose;
  - argumento com valor padrão vira obrigatório no MCP (confirmado).
- **Achados da instalação real:**
  - `Registration` fica em `toolset_registry.registration`;
  - recarregar sem desregistrar deixa uma classe inválida ("Invalid Toolset Class"); corrigido, e `reload_toolset` evita reiniciar o editor.

### Bloco 2 — escada vertical e experimento Sequencer (06/10)
- **Escada vertical:** V01–V07 no banco, 5 capacidades novas no mapa; mapa de lacunas em `docs/MAPA_LACUNAS_V.md` (a lacuna é mecanismo, não clipe).
- **Experimento A (Sequencer) aprovado:** bloco `andar` com avanço medido 644 cm contra previsto 643 cm, saltos de quadril ≤ 7 cm nas trocas, MP4 gerado e limpeza total. Sequencer adotado como caminho principal; Play só para física.
- **Movimentos prontos** (`unreal_macros/blocos.py`, testes offline 3/3): `andar(distância)`, `levantar()`, `compor(...)`, com números medidos por `clip_info`.
- **V03 4/4** (porta empurrada pelo corpo; pré-condição medida e codificada: vão ≥ 150 cm, dobradiça à esquerda). `bone_position_in_clip` corrigida: agora no espaço do corpo e por quadro (antes devolvia relativo ao osso pai e podia disparar o ensure `bValidTime`).
- **V01 5/5 e V02 4/4 no Unreal** (`tools/bloco2_v.py`), com vídeo, câmera que acompanha e cenário visível (`also_show`, `center_bone`).
- **DirectorTools:** `seq_build` (receita de passos com giro opcional; substitui `seq_chain_clips`), `clip_info`, `seq_eval_frame`, `seq_close_delete`; `bone_position_in_clip` recusa tempo fora do clipe (antes disparava um ensure `bValidTime` no editor).

## v0.0.2 — "o Hermes percebe que emperrou, sabe o que fazer e não desperdiça horas" (CONGELADA em 06/10; validação real incompleta)

### Bloco 1 — base estável (promove só o que foi provado no sandbox)
- **deriva_xy pelas pernas** (exp2, Hermes): corrige o falso-FAIL de conversas/gestos parados (Talking_2 21,0 → 4,7 cm no sandbox); Walking continua reprovando.
- **registrar_tentativa** (exp4, Hermes) com duas correções do Claude: diretório fixo (o agente não escolhe onde escrever) e relatório lido do disco por `id` (números não passam pelo LLM; JSON colado fica marcado `fonte=colado`).
- **id + guarda de todo relatório** de macro (`work/relatorios/`).
- **Captura estável** (exp5) disponível e **desligada** por padrão.
- Testes sem Unreal: `src/testes_bloco1.py` (8/8), `src/testes_diario.py` (3/3). Testes no Unreal e paridade de execução: Bloco 5.

### Bloco 2 — trava verificável e controlador de experimentos
- **Trava com dono verificável** (`unreal_macros/trava.py`): pid + horário de criação do processo + host + nonce. Assume/libera só com dono comprovadamente morto (inexistente, terminado ou pid reaproveitado); idade nunca é prova; corrompida exige `corrompida=True`; travas antigas (v0.0.1) tratadas de forma conservadora. Ferramenta `liberar_trava_orfa`; decisões em `work/trava.log`.
- **Controlador de experimentos** (`iniciar/rodar/fechar_experimento`): hipóteses estruturadas e distintas, conserto, apostas com meta/prazo/critério, dependências integradas, worktree próprio, 2 corridas/60 min, guarda intacta, resultado da ferramenta, alternativas guardadas, eventos em disco. Ver `docs/EXPERIMENTOS.md`.
- Testes sem Unreal: `testes_bloco2.py` 21/21 (+ bloco 1 8/8, diário 3/3).

### Bloco 3 — detector de emperramento, skill resolver-problemas, lições e fontes
- **Caracterização antes do código** (`testes_bloco3_caracterizacao.py`): achou 4 lacunas nos registros e corrigiu na ORIGEM — relatório passa a guardar os argumentos da chamada (`chamada`, o alvo); trava ocupada vira espera estruturada (`espera`, exceção `TravaOcupada`); controlador grava `corrida_iniciada` (corrida em andamento visível) e o `script` no evento de corrida.
- **Detector** (`unreal_macros/emperramento.py`): lê só relatórios e eventos das ferramentas; assinatura normalizada (ação, alvo, resultado, classe do erro, estado) sem metadados voláteis; repetição (2ª), vai-e-volta (4º), mesmo erro (2º), estagnação (3ª); esperas declaradas não contam; progresso = melhora medida sobre a melhor tentativa da mesma ação; registros incompletos não entram; escada cutucar → replanejar → outro_caminho → escalar → abortar; disparos gravados de forma idempotente.
- **Orientação** (`unreal_macros/resolver.py`): tipo de falha por tabela fixa, contorno, até 3 lições relevantes, fontes disponíveis × reservadas; não recalcula a detecção; nenhuma porta para texto virar progresso.
- **Skill** `docs/skills/resolver-problemas/SKILL.md` (curta). **Lições** iniciais comprovadas em `docs/licoes_iniciais.json`; votos só por evento do detector (`work/licoes/`). **Fontes** em `docs/fontes_solucoes.json` (3d-asset-server reservado, não instalado).
- Ferramentas novas: `consultar_emperramento(linha)`, `registrar_uso_licao(licao_id, linha)` (20 no total).
- Bugs achados no caminho: falso positivo de "repetição" em consultas idênticas bem-sucedidas (visto nos relatórios reais); inversão de ordem de eventos no mesmo segundo.
- Testes sem Unreal: bloco3 16/16, bloco3b 11/11, caracterização 11/11 (+ bloco1 8/8, bloco2 21/21, diário 3/3; testes antigos sem alteração).

### Bloco 4 — direção, fila por valor, supervisor, passagem de sessão e rotação
- **Origem:** relatório traz `ambiente.versao_codigo` (impressão digital do pacote; base da regressão); `PAUSA` do supervisor é respeitada pelas macros e pelo controlador; experimento declara `pedido` (id do banco ou `infraestrutura/transversal`); evento `escalada`.
- **Banco de pedidos v0** (`docs/pedidos_v0.json`, 20 pedidos, níveis 1–2) e **mapa de capacidades** (`docs/capacidades.json`): disponível/parcial só citando ferramenta MCP que existe no servidor; ir até ponto, porta, escada, sentar e construir lugar como inexistentes. Hoje: 8 atendíveis, 1 parcial, 11 não atendíveis.
- **Fila por valor** (`direcao.montar_fila`): exploração não repete resultado conhecido nesta versão do código (salvo confirmação/desempate com referência verificável); regressão mantém os casos do contrato e os devolve à fila quando o código muda.
- **Supervisor** (`unreal_macros/supervisor.py`): trava órfã / macro presa; 45 min sem progresso útil (só eventos de ferramenta; resultado novo ignora o alvo; mudança real de degrau; experimento fechado; esperas e escalada suspendem o relógio); violações (produção, guarda do sandbox, tentativa proibida) escrevem PAUSA; visão de SESSÃO pega a mesma estratégia com nomes diferentes. Alarmes idempotentes em `work/supervisor/alarmes.jsonl`.
- **Passagem de sessão** (`sessao.passagem`, ferramenta `passagem_de_sessao`): estado mínimo (<= 4 KB) lido do disco; ferramenta `registrar_escalada`. 22 ferramentas.
- **Rotação** (`unreal_macros/rotacao.py`): arquiva (nunca apaga) relatórios com mais de 7 dias que não estão na janela do detector (linha ou sessão), em experimento aberto ou em lição sem voto; índice consultável; `carregar_relatorio` lê do arquivo.
- Bugs achados: degrau antigo exibido depois de progresso; lição duplicada na passagem; motivos de proteção perdidos (agora todos registrados).
