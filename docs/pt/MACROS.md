# Macros do Hermes no Unreal (`florentia-macros`)

*v1, 2026-10-05. Política: `POLITICA_FERRAMENTAS.md`. Inventário: `INVENTARIO_MCP.md`.*

**Código:** `<repo>\src\unreal_macros\` (cópia versionada em `<vm>`).

**Servidor:** `<repo>\venv\Scripts\python.exe <repo>\src\servidor_macros.py` (MCP por stdio, 12 ferramentas).

## Ferramentas

| Ferramenta | O que faz | Muda a cena? |
|---|---|---|
| `inspecionar_cena(filtro)` | lista personagens: rótulo, posição, animação, flags | não |
| `medir_personagem(ator)` | pose pela silhueta (cópia no estúdio): altura, deitado?, pés no piso real; distância aos vizinhos | não mexe no personagem, mas cria cópia e piso temporários (`TESTE_ESTUDIO_<pid>_*`) e move a câmera (devolvida no fim) |
| `buscar_clipe(texto)` | busca na biblioteca Mixamo local (2.317 clipes) por palavras em inglês | não |
| `previa_clipe(nome)` | imagem com 3 quadros do clipe, para a visão conferir antes de importar | não |
| `importar_clipe(nome)` | importa da biblioteca (versão com malha), sem duplicar | cria asset em `/Game/_AnimLab/Mixamo` |
| `aplicar_clipe(ator, clipe)` | aplica clipe a personagem de pé sem mover o ator; corrige orientação (roll 90 dos clipes da biblioteca) e altura medindo | sim |
| `restaurar_animacao(ator, estado)` | desfaz `aplicar_clipe` | sim |
| `capturar_evidencia(ator, vista)` | foto enquadrada por projeção, sem oclusão de cenário | só a câmera |
| `plateia_em_loop(atores, ...)` | workflow: loop discreto em cada um, **um por vez**, para no primeiro que falhar | sim |
| `validar_cartao(cartao)` / `executar_cartao(cartao)` | plano de cena em JSON (sem quadros, sem API) | executar: sim |
| `chamada_avancada(...)` | escotilha SÓ DE LEITURA (recusa escrita e script; registra tentativa, resultado e erro) | não |
| `registrar_falha(titulo, texto)` | grava a FALHA no `FALHAS_UNREAL.md` pela VM (commit) e refaz o cache do Y: se preciso | não (escreve na VM) |

## Gates (todos numéricos; `gates.py`)
- `silhueta_de_pe`: altura da silhueta entre 150 e 200 cm e não deitado.
- `pes_no_chao`: |gap| ≤ 4 cm em relação ao **piso real** sob o original.
- `ator_parado`: o ator não sai do lugar; só se aceita o ajuste que a macro declarou.
- `deriva_xy`: o corpo não "passeia" (4 instantes do clipe, vista lateral).
- `pes_plantados`: IoU das pernas entre instantes ≥ 0,55. Calibração: `Walking` 0,00; conversas 0,69–0,82.
- `distancia_vizinhos`: ≥ 45 cm entre as bases.
- `enquadramento` / `sem_oclusao_cenario` (captura).

## Por que a pose é medida pela silhueta, e no estúdio
- A caixa envolvente do Unreal **não acompanha a pose** dos clipes da biblioteca: um boneco deitado "media" 180 cm.
- O "estúdio" (ideia do Talis) é uma zona neutra em (10000, −3000). Uma **cópia** do personagem, com a mesma malha, animação e rotação, é fotografada com e sem ela. A diferença é a silhueta. Ninguém fica na frente e o original não é tocado.
- Uma régua de alturas projetada na mesma câmera converte pixels em cm.
- Calibração: pés no piso medem −9 cm (perspectiva), compensados por `CALIB_PES_CM`.

## Descobertas que viraram regra dentro das macros
1. **Clipes da biblioteca** (`animation_motion_ybot`) vêm **deitados 90°** (export do Blender). Correção: componente com **roll +90**. Validado por foto: de pé, olhando +Y no yaw 0, compõe com o yaw. Clipes do site (`..._mixamo_com`): roll 0.
2. Atores criados por spawn têm o componente animado como raiz; os do LAB, não (a posição fica no componente).
3. O editor não toca o loop em tempo real de forma confiável: para medir movimento, a cópia é **congelada em instantes** do clipe.
4. O `Talking_2` é uma conversa de pé, parada. O Hermes o reprovou porque o mediu deitado.

## Testes
- `src/testes_contrato.py`: 14 casos, incluindo controles negativos (sem roll 90 → deitado reprova; vizinho colado reprova; escotilha recusa salvar a sala).
- `src/testes_workflow.py`: plateia com 3 bonecos; controle `Walking` (anda) tem de parar o workflow; cartão medir + capturar.
- Tudo na zona de testes (x = 10000), com atores `TESTE_*` apagados no fim; o LAB nunca é salvo.

## Garantias e limites (revisão do Astra, 06/10)
- Uma macro por vez: trava em `work/unreal.trava` (entre processos das macros; o Hermes antigo/outros agentes não a respeitam).
- Prazo total por macro: 1500 s; cada requisição 45 s; timeout = ESTADO DESCONHECIDO (rode `inspecionar_cena` antes de repetir; não há cancelamento dentro do Unreal).
- `aplicar_clipe` restaura e confere o estado anterior se qualquer gate reprovar ou der erro; depois do ajuste de Z ele MEDE DE NOVO.
- Família do clipe por nome exato: `..._mixamo_com` (site) ou `<Nome>_Anim` da biblioteca; qualquer outro é recusado.
- Atores com escala ≠ 1 ou inclinação são recusados (a cópia do estúdio não os reproduz).
- `deriva_xy` usa 4 instantes em 2 vistas (lateral + frontal); movimento ENTRE os instantes pode passar. `pes_plantados` compara a região das pernas, não mede contato nem deslizamento do pé.
- `enquadramento` de `capturar_evidencia` ainda usa a caixa envolvente.

## Limites conhecidos
- **Sentar** ainda não é macro (receita R-13 manual); `aplicar_clipe` é só para personagem de pé.
- **Sequencer** (encadear clipes no tempo) ainda não é macro: está bloqueado pela FALHA-19 e pela falta de amostragem de osso.
- A duração de clipes do site (`..._mixamo_com`) é assumida como 2 s nas amostras de movimento.
