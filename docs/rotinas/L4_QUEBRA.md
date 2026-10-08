# L4: tentar quebrar uma entrega (rotina do hermes-dev)

> Linha 4 do [PLANO_PROXIMA_VERSAO.md](../PLANO_PROXIMA_VERSAO.md). Quem chama é o Claude, depois de uma entrega: até 3 rodadas, e para antes se uma rodada não achar quebra nova. O Claude lê só o `RESUMO.json` e o relato.

**Como chamar** (sessão nova, em segundo plano):
```
hermes -p hermes-dev chat --query-file <este pedido preenchido> -Q --max-turns 60 --run-budget 1800 --in <repo>
```
Ambiente da sessão: `UNREAL_MACROS_OFFLINE=1`. O cliente da 8001 recusa conectar.

---

## Pedido (preencha os campos entre `< >`)
Use a skill `bateria-python`.

**Entrega:** `<escaladas/AAAA-MM-DD-ENTREGA-tema.md>`, commit `<hash>`.

1. Rode a bateria no commit atual e leia o `RESUMO.json`.
2. Leia as **invariantes** da entrega (as regras que nunca podem quebrar).
3. Para cada invariante que a bateria ainda não testa, escreva uma **proposta** de propriedade Hypothesis em `work/bateria/propostas/<data>-<tema>.md`, com:
   - a invariante, em uma frase;
   - a função testada (`arquivo:função`);
   - a estratégia de entradas, incluindo os valores "estranhos": NaN, infinito, zero, negativo, vazio;
   - o caso que **tem de reprovar**.
4. **Pode** testar a proposta numa cópia fora do repositório, em `work/bateria/propostas/<tema>/`. Se ela achar uma quebra, relate o **menor exemplo que falha** e o comando para reproduzir.
5. **Não mude** a régua (ver a skill) nem o código da entrega.

**Saída:** `work/bateria/propostas/<data>-<tema>-RELATO.md`, com:
- a bateria (ok, commit, marco);
- as quebras achadas (menor exemplo, arquivo:linha, comando);
- as propostas escritas.

Responda em no máximo 10 linhas.

**Depois (Claude):** cada quebra confirmada vira teste permanente na suíte certa, e a proposta boa entra em `src/testes_propriedades.py`.
