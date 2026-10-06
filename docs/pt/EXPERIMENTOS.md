# Controlador de experimentos (v0.0.2)

Ferramentas MCP: `iniciar_experimento`, `rodar_experimento`, `fechar_experimento` (código: `src/unreal_macros/experimentos.py`).

| Regra | Como é garantida |
|---|---|
| Experimento só com solução incerta | 2–3 hipóteses `{descricao, mudanca, previsao}`; reformulação recusada (similaridade de radicais >= 0,5 — heurística determinística; paráfrase com vocabulário todo diferente escapa) |
| Causa comprovada = conserto | `tipo=conserto`: sem hipóteses, com `causa_evidencia` existente (relatorio_id ou arquivo do sandbox) e `correcao` |
| Aposta | `aposta: {meta:{metrica, comparador, valor}, prazo_min (1–60), criterio_encerramento}`; o prazo da aposta limita o experimento |
| Nada se perde | hipóteses não escolhidas vão para `work/experimentos/alternativas.jsonl` |
| Dependências | branches do sandbox que precisam estar integradas no `master` (`git merge-base --is-ancestor`) |
| Sem trocar de branch na pasta compartilhada | cada experimento ganha `git worktree` próprio em `<sandbox>-exp/<nome>`, criado do `master` |
| Limites | 2 corridas; 60 min desde o início; cada corrida até 25 min (teto da ferramenta MCP) |
| Sem caminho novo para fora da guarda | só script dentro da cópia; `PYTHONPATH` = cópia; recusa se `guarda.py` difere do master; recusa scripts que citam a produção, o MCP bruto (`127.0.0.1:8001`), `_call_cru` ou a variável da trava; remove variáveis de trava do ambiente. O terminal do agente continua fora do alcance do controlador. |
| Resultado é da ferramenta | código de saída, duração, `N/M testes ok` e `relatorio_id` lidos da saída; a interpretação do agente fica em `interpretacao_declarada` |
| Histórico | `work/experimentos/eventos.jsonl` (iniciado, corrida, recusa, fechado) — consumido pelo bloco 3 |
