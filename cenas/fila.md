# Cena: fila de movimentos

> Modelo de cena da linha 2 (Fase 8). **O Talis edita este arquivo**; o `tools/linha2.py` o lê e gera o pedido do Productor.
> Uma linha por campo, no formato `- campo: valor`. Os critérios só podem vir do catálogo da régua de hoje (o comando avisa se faltar).

- nome: fila
- descricao: Num boneco só, levantar de uma cadeira, acenar, andar e parar em pé.
- papeis: levantar, acenar, andar, parar
- pode_variar: clipes, pontes, giros (turn_deg e turn_fim_deg), início e corte do clipe, número de passos de caminhada
- fixo: a ordem dos papéis; um boneco só; nada salvo no Unreal
- criterios: levantar, acenar, andar, parar, trocas, duracao
- variacoes: 3
- prazo_tentativas: 07:30
- ate: 08:00
