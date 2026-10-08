# L1: o olhar de júnior (rotina do hermes-dev)

> Linha 1 do [PLANO_PROXIMA_VERSAO.md](../PLANO_PROXIMA_VERSAO.md), Fase 9.
> **Situação (08/10):** esta rotina e o conferidor (`tools/conferir_ideias.py`) estão prontos.
> **1º passo feito (08/10):** a busca na web e o Context7 respondem no `hermes-dev` (sessão 20261008_134511_790ce3). **1ª rodada feita (08/10):** tema 1, 5 ideias, conferidor aprovou e os números conferem (sessão 20261008_134610_39ddc1, 11,4 min).

**Quem chama:** o Claude, a cada versão, ou quando o Talis pedir. O tema vem da lista em [temas.md](temas.md): o primeiro sem data de uso, ou o que o Talis escolher.

**Como chamar** (sessão nova, em segundo plano):
```
hermes -p hermes-dev chat --query-file <este pedido preenchido> -Q --max-turns 60 --run-budget 1800 --in <repo>
```

**Mede:** quantas ideias o Talis aprova por rodada. Se ficar perto de zero, a frequência cai.

---

## Pedido (preencha `<tema>` e `<data>`)
Você é o "olhar de júnior" do Director: olhe o projeto com olhos novos e traga **até 5 ideias** sobre o tema **<tema>**. Não escreva código nem mude arquivos do projeto; escreva só o arquivo de saída.

1. **Leia antes:**
   - `docs/ESTADO_ATUAL.md`;
   - `docs/PENDENCIAS.md`: ideia repetida de uma pendência aberta é recusada;
   - os arquivos do código ligados ao tema.
2. **Biblioteca Python: use o Context7 sempre**, antes de propor qualquer ideia que envolva uma biblioteca:
   - confira a versão **instalada** no `pip freeze` do venv certo: `venv\` (Runtime) ou `.venv-ferramentas\` (ferramentas);
   - peça ao Context7 a documentação **dessa versão**. Há relatos de ele trocar de biblioteca: confira o nome;
   - **o Context7 é fonte auxiliar, não verdade.** Confira o que ele disser contra o código do repositório;
   - se o Context7 não responder, escreva isso no arquivo e siga sem ele. **Não invente documentação.**
3. **Internet:** toda ideia que vier de uma página traz o link e um trecho copiado entre aspas.
4. **Escreva** `ideias/<data>-<tema>.md` **exatamente** neste formato:
   ```
   # Ideias: <tema> (<data>)
   ## 1. <título curto>
   - **Problema:** <o que hoje dá errado ou custa caro>
   - **Ideia:** <o que fazer, em 1-3 frases>
   - **Evidência:** `arquivo.py:linha` (que existe) ou um número com unidade (ex.: 138 trocas, 6 min)
   - **Fonte:** https://... — "trecho copiado"            (só se veio da internet)
   - **Biblioteca:** nome==versão-instalada — "trecho"     (só se envolve biblioteca)
   - **Custo:** baixo | médio | alto
   ```
5. **Confira:** `.venv-ferramentas/Scripts/python.exe tools/conferir_ideias.py ideias/<data>-<tema>.md`.
   - Se reprovar, corrija **uma vez**.
   - Se reprovar de novo, deixe como está e diga o motivo.
6. **Responda** em no máximo 8 linhas: as ideias (título e custo) e o resultado do conferidor.

**Proibido:**
- usar o Unreal ou a porta 8001;
- mudar código, docs, régua ou perfil;
- escrever fora de `ideias/`. Rascunho e script de teste vão só na pasta de rascunho do próprio Hermes (`profiles/hermes-dev/cache/scratch`), nunca em outra pasta do projeto, nem no `unreal-macros-sandbox` (na 1ª rodada, 08/10, um arquivo de teste foi parar lá e foi apagado pelo próprio júnior).
