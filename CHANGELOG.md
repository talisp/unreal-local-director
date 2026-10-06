# Changelog

## v0.0.2 — "o Hermes percebe que emperrou, sabe o que fazer e não desperdiça horas" (em construção)

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
