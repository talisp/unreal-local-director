# L2: cena completa com variações (protocolo do Productor)

> Linha 2 do [PLANO_PROXIMA_VERSAO.md](../PLANO_PROXIMA_VERSAO.md), Fase 8. **Quem roda é o Qwen no `codex-unreal-economico`; quem lança é o Talis**, com `tools/linha2.py` (ensaio ou noite). O Claude não roda o ensaio.
> O texto abaixo da linha é o modelo: o `tools/linha2.py` troca os `{campos}` pela cena (`cenas/<nome>.md`) e pelas partes geradas por script (comandos, ferramentas e critérios de hoje). Mudou o protocolo? Mude aqui, nunca no pedido gerado.

---
[Mensagem gerada por `tools/linha2.py`, a pedido do Talis.] **Rodada do Productor: cena "{nome}"{modo}.** {descricao}

Para: o Productor (perfil `codex-unreal-economico`, Qwen), conversa nova. Até **{ate}**; às **{prazo}** o executor para de aceitar tentativas e você escreve o fechamento. Uma vigia acompanha a rodada e, se a sua sessão parar no limite, abre uma sessão nova com este mesmo pedido e o estado gravado: **comece sempre pelo `estado`**.

## 0. Antes de tudo
- **Terminal (Bash).** Todo comando do executor é exatamente assim:
  `{cmd} <comando>`
  Nunca grave nada em `Y:` (regra 9 da sua skill). O `Y:` serve só para ler a biblioteca de clipes (`<shared drive> Unreal/Animacoes/Mixamo/metadata.csv`).
- **Exceção autorizada pelo Talis, só nesta rodada:** a regra 8 da sua skill `unreal-macros` ("Sentar e Sequencer estão BLOQUEADOS") não vale aqui. O Sequencer é usado **só pelo executor**, que pega a trava e limpa a cena.
- **Não fale com o Unreal de outro jeito:** nada de MCP bruto, de `chamada_avancada` para escrever ou de script seu tocando a cena.

## 1. A cena
- **Papéis, nesta ordem (fixa):** {papeis}.
- **Pode variar:** {pode_variar}.
- **Fixo:** {fixo}.
- **Critérios (a régua do programa; você não muda):**
{criterios}

## 2. Ferramentas que existem hoje (geradas pelo script)
{ferramentas}

**Primeiro a biblioteca, depois o Unreal.** Antes de cada tentativa, consulte `consultar_trocas(clipe_de, papel_para)` para os pares que vai usar. A mesma troca custa o mesmo em qualquer receita: troca já medida e ruim não se tenta de novo.

**Receita** (um arquivo JSON seu em `{pasta}/`, por exemplo `{pasta}/proposta.json`):
```json
{receita_exemplo}
```
`tipo` = `ajuste` (muda uma coisa na melhor da linhagem; `de` = o número dela) ou `exploracao` (ideia diferente, ou linhagem nova).

## 3. O ciclo
1. `estado`: as campeãs, as linhagens, a tentativa rodando, as últimas notas e a fase (sucesso ou variações).
2. Consulte a biblioteca, pense e escreva a receita (com a hipótese).
3. `tentar {pasta}/proposta.json`: responde na hora com o número N; roda sozinha (5 a 20 min).
   Se vier `"recusada"`, leia o motivo e mude a receita: **as regras estão no programa**.
4. `resultado N`: a nota (0 = passou), o que falhou, as trocas e `cena_ok`.
5. Uma frase em `{pasta}/LICOES.md` quando aprender algo (no máximo 15 linhas).
- **Linhagem em platô:** `fechar-linhagem A "motivo"` e abra outra.

**Fase 1, sucesso:** a mesma receita com nota 0 **três vezes** (o `estado` mostra `sucesso`).
**Fase 2, variações ({variacoes}):** depois do sucesso, faça {variacoes} receitas que **passam** e são **diferentes de verdade**:
- marque cada uma com `"variacao": true`;
- cada uma precisa de clipe diferente em pelo menos um papel, em relação à de sucesso e às variações já aceitas. Mudar só ponte ou giro não conta, e o programa recusa;
- toda variação sai com vídeo, para o Talis escolher.
{ensaio}
## 4. Pare (e escreva o fechamento) quando
- `resultado` com `"cena_ok": false` ou `classe_erro: "estado_parcial"`: **pare tudo** (regra 10 da sua skill);
- o executor recusar por hora, por 80 tentativas, por 6 linhagens ou porque as variações estão completas;
- `{pasta}/criticas.md` disser duas vezes seguidas que não há progresso (escreva 5 linhas nele a cada 15 tentativas).

## 5. Fechamento e registro
- **`{pasta}/FECHAMENTO.md`**, em português simples:
  - conseguiu ou não, com as notas;
  - a receita de sucesso e as variações, com os vídeos;
  - as trocas difíceis e o que resolveu;
  - o que faltou de ferramenta (`capacidade_ausente`, com número).
- Depois do fechamento: `{escolha}` (prepara a escolha do Talis).
- **Uma linha** no fim de `<repo>/docs/REGISTRO.md`.
- **Não edite** código (`src/`, `tools/`, `editor_python/`), não faça commit nem push, não mexa em perfil do Hermes.
- **Nunca invente número:** tudo vem do `resultado` e do `estado`.

**Comece por:** `docs/TALIS.md` (inteiro), as últimas 15 linhas de `docs/REGISTRO.md` e `estado`.
