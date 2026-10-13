# Resultados da v0.0.6 (corretiva)

> Só números agregados. Os registros completos (logs RED/GREEN de cada lote, fotos da cena, amostras do ensaio) ficam em `work/v006-retomada/` (local, fora do git).

- **O que foi feito:** 7 lotes (L0–L6) com as correções da auditoria Astra de 10/10 e dos itens herdados, mais o fechamento (L7). Cada lote tem um teste que reproduz o defeito no código anterior (controle negativo) e passa depois da correção.
- **Onde estão os números:** [RESULTADOS.json](RESULTADOS.json).
- **Ensaio no Unreal real (11/10, 20:06–20:13):** uma tentativa do executor com a receita do bloco `fdb93eafc4a5`: nota 0, tentativa aprovada, cena idêntica (86 → 86 atores, comparados em caminho, rótulo, classe, posição, rotação e escala), os 4 passos da limpeza confirmados, trava livre.
- **Primeira noite real (11→12/10):** 7 h 04 min, 28 tentativas, 28 com a cena restaurada, nenhuma falha do programa, 11 aprovadas com nota 0 e 17 reprovadas pela régua. O modelo local fechou a campanha 25 min antes do prazo dizendo que não havia mais o que testar; por isso, em 13/10, entrou o modo de teste da versão (16 testes offline; ainda não rodou ao vivo).
- **O que este resultado não prova:** que o bloco está validado de novo (são 3 tentativas), a autonomia do Qwen numa noite, o vídeo e outras malhas.
