# L3: o Astra (Codex) como auditor pontual

> Linha 3 do [PLANO_PROXIMA_VERSAO.md](../PLANO_PROXIMA_VERSAO.md), Fase 7. **Cada chamada gasta cota: só com o "sim" do Talis.**
> **Quando chamar** (só nestes 4 momentos):
> 1. antes de uma rodada de noite nova;
> 2. antes de publicar;
> 3. depois de uma versão grande;
> 4. quando alguém trava 2 vezes no mesmo problema.

**Como chamar:** `tools/astra.py`.
- Sem `--enviar`, só monta e mostra o pacote (não gasta nada).
- Com `--enviar --confirmo-cota`, chama pelo `hermes-dev`, que roda o Codex CLI em modo **só leitura** e grava a resposta.

**Depois:** o script confere o formato da resposta e grava `escaladas/<data>-ASTRA-<tema>.md`, com o commit revisado. O Claude mapeia **item por item** para onde cada achado foi parar (skill, lição, código ou pendência; lição 16).

---

## Pedido ao Astra (o script cola o pacote no fim)
Você é o Astra, auditor do projeto Director. Responda **uma pergunta só** (abaixo), olhando o repositório em modo só leitura.

**Regras:**
- **Não edite nada**, não rode git, não use o Unreal nem a porta 8001.
- Abra só os arquivos da lista "Arquivos que você pode abrir" do pacote. Se precisar de outro, diga qual e por quê, sem abrir.
- Todo achado precisa de prova `arquivo:linha` que exista. Achado sem prova não conta.
- Diga se você **verificou** o achado (leu o código e conferiu) ou se é suspeita.
- No máximo **600 palavras** fora do bloco JSON.

**Responda terminando com UM bloco assim** (é o que o script lê):
```json
{"pergunta": "<repita a pergunta>",
 "achados": [{"achado": "<o problema, em 1 frase>", "gravidade": "alta|media|baixa",
              "prova": "<arquivo>:<linha>", "correcao": "<o que fazer, em 1 frase>", "verificado": true}],
 "resumo": "<1 frase>"}
```
Se não achar nada, `"achados": []` e diga no resumo o que olhou.
