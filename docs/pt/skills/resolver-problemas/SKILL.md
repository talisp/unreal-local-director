---
name: resolver-problemas
description: "Use quando consultar_emperramento disser emperrado=true, ou quando uma tarefa falhar duas vezes: diz o que fazer em cada degrau (cutucar, replanejar, outro caminho, escalar, abortar)."
version: 0.0.2
---

# Resolver problemas

**Quem decide se você emperrou é a ferramenta, não você.** Chame `consultar_emperramento(linha)`. Ela lê os relatórios e os eventos das ferramentas e devolve `emperrado`, `degrau`, `tipo_falha`, `contorno`, `licoes` e `fontes`. Escrever "estou progredindo" ou "estou emperrado" não muda nada: só um resultado novo, medido pelas ferramentas, conta.

## 1. Ficha do problema (5 linhas, no começo e a cada degrau)
1. Objetivo em uma frase.
2. Como vou saber que resolvi? (critério medido por ferramenta)
3. Fatos (com relatorio_id ou evento) × suposições.
4. Problema parecido já resolvido? (as `licoes` devolvidas)
5. Menor passo que testa a suposição mais arriscada.

## 2. O que fazer em cada degrau (o degrau vem da ferramenta)
| Degrau | Faça |
|---|---|
| `cutucar` | Diga em 1 linha o padrão (ex.: "repeti a mesma corrida com o mesmo erro"). Aplique o `contorno` do `tipo_falha`. |
| `replanejar` | Refaça a ficha. Leia as `licoes`. Pesquise a ESTRATÉGIA (não o erro pontual) nas `fontes` disponíveis. Decida entre: nova hipótese, voltar à dependência, abandonar. |
| `outro_caminho` | Abandone a abordagem: use uma hipótese do arquivo de alternativas (work/experimentos/alternativas.jsonl) ou um caminho bem diferente. |
| `escalar` | Registre o diagnóstico e chame o Claude (ou o operador). Pare a linha. |
| `abortar` | Feche com registro (fechar_experimento) e mude de tarefa. |

## 3. Tipos de falha (o `tipo_falha` vem da ferramenta)
entendimento · conhecimento · capacidade · ambiente · verificacao · dependencia · estrategia — o `contorno` de cada um vem junto. Duas regras que valem sempre:
- **Solução incerta** = experimento com 2–3 hipóteses diferentes (`iniciar_experimento tipo=experimento`).
- **Causa comprovada com correção direta** = `tipo=conserto` (sem hipóteses, com a evidência).
- **Antes de construir do zero**, use as `fontes` disponíveis. Fonte "reservada" (não instalada, ex.: 3d-asset-server) **não pode** ser usada.
- Quando uma lição ajudar, chame `registrar_uso_licao(licao_id, linha)`: o voto sai sozinho do próximo resultado.

## 4. Exemplo real (exp3, 06/10)
"Balança única" dependia do exp2, que estava em outra branch. Foram 4 corridas do contrato, com merge na mão e trava apagada, em 1,5 h sem resultado novo. Com a v0.0.2:
- a 2ª corrida igual vira `repeticao`, e a ferramenta indica o degrau `cutucar` com o contorno de `estrategia`;
- a dependência não integrada já é recusada no `iniciar_experimento`, que indica `dependencia` e o contorno "voltar à dependência e pedir integração";
- a lição L-dep-01 aparece sozinha.
