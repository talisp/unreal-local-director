# Prompt: bancada de testes do Hermes (sessão longa, gera dados)

Cole no Hermes (perfil `codex-unreal-economico`), já reaberto. Primeiro o `/goal`, depois a mensagem.

## /goal

```
/goal Rodar por horas uma bancada de testes de movimentos no Unreal com as macros florentia-macros: escolher clipes da biblioteca local, testar, medir, registrar cada tentativa (acerto e erro) num diário JSONL e devolver a cena como estava. Não é para produzir animação final; é para gerar dados sobre os limites do sistema.
```

## Mensagem

```
Leia a skill unreal-macros antes de tudo e siga a política dela (só macros; a escotilha chamada_avancada só lê).

FASE 0 (primeiros 60 minutos): o Claude está terminando testes no Unreal. NÃO chame nenhuma macro que usa o Unreal (inspecionar_cena, medir_personagem, importar_clipe, aplicar_clipe, capturar_evidencia, plateia_em_loop, executar_cartao, chamada_avancada) antes de 60 minutos desta mensagem; confira a hora pelo terminal. Nesse tempo: pesquisa na internet/GitHub (temas abaixo), buscar_clipe e previa_clipe (não usam o Unreal) e escreva no diário a lista de ~60 clipes candidatos com a sua PREVISÃO para cada um. Se depois disso uma macro disser "Unreal ocupado por outro operador", espere 10 minutos (sleep no terminal) e tente de novo; registre a espera no diário.

OBJETIVO: você é uma BANCADA DE TESTES, não um animador. Quero horas de experimentos com a biblioteca de movimentos (<shared drive> Unreal\Animacoes\Mixamo, que as macros buscar_clipe/previa_clipe/importar_clipe já leem) e um registro honesto do que funciona e do que quebra. Os dados serão analisados depois pelo Claude e pelo Astra para entender os limites do Unreal, das macros e da sua própria inferência. Um erro bem registrado vale tanto quanto um acerto.

ONDE TESTAR: só nos personagens que inspecionar_cena mostrar no mezanino (filtro "Mezz"). Um ator por vez. DEPOIS DE CADA TENTATIVA, mesmo que tenha passado, devolva o ator ao estado original com restaurar_animacao usando o medidas.antes.props do relatório. A cena tem de terminar exatamente como começou. NÃO salve nada no Unreal.

TEMAS (faça rodadas de ~10 tentativas por tema, e varie):
1. Conversa e plateia: idle, talking, listening, nodding, whispering, arguing, laughing.
2. Gestos de orador: pointing, explaining, arm gesture, presenting, accusing, shrug.
3. Saudação: waving, greeting, bow, salute.
4. Transições (devem REPROVAR ou ser marcadas como "fora do escopo"): sit to stand, stand to sit, start walking, stop walking, turn.
5. Locomoção (controle negativo, deve REPROVAR no deriva/pes_plantados): walking, stairs up/down, walking talking.
6. Clipes difíceis: muitos quadros, mãos acima da cabeça, agachar, ajoelhar.
Para cada tema: buscar_clipe (inglês, com e sem max_quadros), previa_clipe do candidato e vision_analyze da imagem ANTES de importar; escreva sua PREVISÃO (passa/reprova e por quê); importar_clipe; aplicar_clipe; capturar_evidencia quando passar; restaurar_animacao. Às vezes use plateia_em_loop com 2 atores e validar_cartao/executar_cartao com cartões que você escrever (inclua de propósito 1 cartão inválido por rodada para testar a validação).

PESQUISA (GitHub/internet): a cada tema, ou quando algo falhar sem você entender, pesquise com web_search/web_extract (ou pelo terminal: gh search repos / gh search code / gh api) sobre o assunto: Mixamo root motion e orientação no Unreal, retarget, AnimSequence, "in place" vs root motion, FBX axis conversion, Unreal MCP/Python Editor Scripting. Prefira repositórios com código e issues reais. Anote no diário a fonte (URL), o que ela diz em 1-2 frases e se mudou a sua previsão. Não instale nada nem rode código baixado.

DIÁRIO (obrigatório, é o produto principal): acrescente UMA linha JSON por tentativa em
<repo>\work\bancada_hermes\diario.jsonl
com os campos:
{"hora","tema","ator","clipe","quadros","previsao","previsao_motivo","macro","ok","gates":{nome:resultado e valor},"bloqueio","avisos","segundos","restaurado","evidencia","fonte_pesquisa","licao"}
Copie números e mensagens dos relatórios das macros; NÃO invente valor que o relatório não trouxe (deixe null). Ao fim de cada tema, escreva uma linha {"tipo":"resumo_tema",...} com acertos de previsão, erros mais comuns e o que você mudaria nas macros.
Erros de chamada (parâmetro errado, timeout, ESTADO DESCONHECIDO, ferramenta que não existe) também vão para o diário, com a mensagem exata e o que você tentou antes.

APRENDER: antes de cada tema, releia as últimas 30 linhas do diário e diga em 3 linhas o que vai fazer diferente. Não repita um clipe que já reprovou pelo mesmo motivo.

FALHAS: use registrar_falha só para um TIPO de problema novo e reproduzido 2 vezes (no máximo 1 por tema). Nunca edite arquivos .md no Y:.

REGRAS DE SEGURANÇA:
- Timeout ou "ESTADO DESCONHECIDO": pare, rode inspecionar_cena, confira o ator, registre e só então continue.
- Se a restauração não conferir ("ESTADO PARCIAL"), PARE a sessão inteira e me avise.
- Não mexa na sala de audiência, não salve assets, não peça para outro agente mexer no Unreal.
- "Feito" só com ok=true e gates PASS no relatório.

Rode até eu mandar parar. A cada ~1 hora, me mande um placar curto: tentativas, % ok, % previsões certas, 3 principais limitações encontradas.
```

## Para analisar depois (Claude/Astra)
- `work/bancada_hermes/diario.jsonl`: tentativas, previsões e lições.
- `work/escotilha.log`: o que ele tentou fazer fora das macros (= macros que faltam).
- `work/previas/`, `<evidence dir>\`: imagens.
- `baseline.py` de novo: taxa de erro antes e depois.
