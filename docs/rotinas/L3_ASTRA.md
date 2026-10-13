# L3: Astra como auditor pontual — contrato 0.2.0

Cada envio gasta cota e exige “sim” específico do Talis. Manutenção/testes offline não autorizam inferência. Momentos históricos: antes de rodada nova, antes de publicar, depois de versão grande ou travamento técnico persistente. Não é chamada automática.

## Duas fases
A: auditoria sem resultados/conclusões Qwen. Organizador seleciona código/contratos, lê regras superiores e declara seleção informada. tools/astra.py prepara snapshot fora da árvore do repositório, TALIS íntegro e AGENTS neutro. Não enviar HANDOFF/REGISTRO/pendências/AGENTS originais que revelem achados. Não descumprir ordens superiores para conseguir independência; conflito de contrato é bloqueio documentado. Contexto global da CLI e leitura fora da lista continuam limites a conferir, não sandbox garantido.
B: somente após parecer A salvo e congelado, cruzar evidências Qwen/Astra localmente. Não pedir outra inferência Astra para reorganizar relatórios. Comparação por referências é índice, não validação de causa/verdade.

## Instrumento existente
Pelo terminal, Python compatível e `tools/astra.py --help`:
- `--fase preparar --tema <tema> --pergunta "<pergunta>" --arquivos <lista> --base <commit> --modelo <modelo>`: sem inferência.
- `--fase enviar --campanha <pasta> --enviar --confirmo-cota`: somente depois de aprovação explícita do pedido/campanha/modelo.
- `--fase conferir --campanha <pasta>`: fotografia do manifesto, não HEAD atual.
- `--fase retomar --campanha <pasta>`: diagnóstico, nunca reenvio.
- `--fase comparar --campanha <pasta> --relatorios <arquivos>`: fase B local.

Pipeline não usa organizador Hermes adicional; Codex CLI explícito/read-only em snapshot. Pedido final <=14000 caracteres e até cinco arquivos. Excesso bloqueia, nunca corte oculto. Manifesto schema 1 identifica instrumento/skill, commit completo + estado local/hashes, arquivos/linhas/bytes, pergunta/modelo e hash do pedido. Eventos e artefatos novos por campanha; logs/retorno/modelo/parecer ligados. Falha/resposta antiga/interrupção não aprovam entrega.

## Pedido ao Astra (o script mantém o prompt vigente em PROMPT)
Responda uma pergunta, sem editar nem usar Unreal/8001/<shared drive> externos ou credenciais. Leia TALIS inteiro e regras neutras; abra somente código/contratos autorizados. Solicite lacuna sem abrir outro arquivo. Achado deve ter prova canônica arquivo:linha existente na fotografia. “Verificado” significa leitura conferida, não reprodução.

Síntese: até 600 palavras (prosa + resumo), até cinco prioridades opcionais. Todos os defeitos distintos sustentados ficam no JSON técnico, <=64000 bytes, sem máximo cinco nem quota mínima. Uma causa por item; não agrupar para caber. Terminar com UM bloco JSON:
```json
{"pergunta":"<repita exatamente>","achados":[{"achado":"<consequência e causa>","gravidade":"alta|media|baixa","prova":"<arquivo>:<linha>","correcao":"<proposta>","verificado":true}],"resumo":"<síntese>","prioridades":[1]}
```
Pode adicionar `provas` como lista; TODAS devem ser válidas. `achados: []` e `prioridades: []` são permitidos. Não inventar achados; declarar cobertura e limitações.

## Compatibilidade e aceite
Resposta antiga sem manifesto é histórica/incompleta; não normalizar nem regravar. Interface conferir_resposta conserva chaves para leitura legada, mas formato não prova verdade. Chamadores antigos sem lista/campanha são bloqueados antes de gastar; painel/Runtime não foram atualizados nesta manutenção. Usar fluxo da skill, não porta antiga, na próxima auditoria.
Conferir cada achado e ligar destino proposto (teste/correção/pendência) sem implementação automática. Nenhuma LLM aprova a si mesma; Talis decide. Regressores: docs/skills/test_astra_pipeline.py; distribuição: docs/skills/test_skills_agressivas.py. Versão publicada, instalada e efetivamente validada são estados separados; ver referências/evolucao da skill e relatório da manutenção.
