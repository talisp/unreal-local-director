---
name: unreal-macros
description: "Como trabalhar no Unreal do Florentia pelas macros (ferramentas florentia-macros): ler sempre antes de mexer em personagem, animação ou captura."
version: 1.0.0
author: Talis / Claude Code
license: MIT
platforms: [windows]
---

# Unreal pelas macros (florentia-macros)

Você não chama mais as ferramentas pequenas do MCP do Unreal. Cada ferramenta `florentia-macros` faz uma tarefa inteira, confere o resultado com medidas e devolve um relatório:

```
{macro, ok, medidas, evidencias, avisos, bloqueio, chamadas, segundos}
```

## Regras
1. **Só existe sucesso com `ok=true`.** Se `ok=false`, leia `bloqueio` e os `gates` que reprovaram. Não "compense" à mão e não repita igual.
2. **Personagem de pé + animação:**
   - `buscar_clipe` (palavras em inglês) → `previa_clipe` + `vision_analyze` na imagem → `importar_clipe` → `aplicar_clipe`;
   - se `ok=false`, use `restaurar_animacao` com `medidas.antes.props`.
3. **Plateia ou grupo:** use `plateia_em_loop`. Ele já faz um por vez, testa vários clipes e para no primeiro que não der certo.
4. **Medir ou diagnosticar:** use `medir_personagem` (silhueta numa cópia no estúdio).
   - A caixa envolvente do Unreal mente nos clipes da biblioteca: não use bounds para julgar pose.
   - Prova visual: `capturar_evidencia` + `vision_analyze`. A visão é segunda opinião: um NÃO dela no critério principal é FAIL.
5. **Cena com vários passos:** escreva um cartão e rode `validar_cartao` antes de `executar_cartao`. O cartão não tem números de quadro nem nomes de API:
   ```
   {"objetivo": "...", "deve_evitar": ["..."],
    "passos": [{"id": "p1", "acao": "medir_personagem", "ator": "PC_18_Mezz01"},
               {"id": "p2", "acao": "aplicar_clipe", "ator": "PC_18_Mezz01", "clipe": "Head_Nod_Yes", "depois": "p1"}]}
   ```
6. **Nunca mova o ator** que o Talis posicionou. As macros só ajustam o componente pelo que mediram e declaram isso.
7. **`chamada_avancada` só LÊ** (get/find/list/describe/trace...). Ela recusa qualquer escrita ou script. Se precisar mudar algo que nenhuma macro faz, use `registrar_falha` para pedir a macro e avise o Talis.
8. **Sentar e Sequencer estão BLOQUEADOS** (não há macro; FALHA-19 aberta). Responda que está bloqueado e pergunte ao Talis. Não improvise e não siga receita manual.
9. **Nunca edite arquivos `.md` do projeto pelo Y:** (o drive sincronizado zera o arquivo: FALHA-23). Para registrar uma falha use `registrar_falha` (grava pela VM com commit). Se o Unreal não responder, as macros avisam em 45 s: feche diálogos abertos e repita UMA vez.
10. **"ESTADO PARCIAL" ou restauração que não conferiu = PARE A SESSÃO.** Não tente restaurar de novo nem siga com outro ator. Registre o `antes.props` e o erro exato, e escreva só: "PARADO POR BLOQUEIO: <motivo>". (06/10: insistir depois de estado parcial violou esta regra.)
11. **Timeout ou "ESTADO DESCONHECIDO" numa macro:** rode `inspecionar_cena`, confira o ator e NÃO repita o mesmo clipe em nenhum ator naquela sessão.
12. **Ordem de duração vale mais que "objetivo cumprido":** se a tarefa diz "até HH:MM" ou "até eu mandar parar", não encerre antes. Ao achar que terminou, passe para o próximo item da lista ou repita casos em outros atores.
13. **Gates novos (06/10):** `aplicar_clipe` mede 4 instantes do clipe (`pose_em_todo_clipe`, `pes_plantados`). Ajuste de altura acima de 10 cm não é feito: vira aviso e reprova. Silhueta incompleta não mede (`motivo` no relatório).
