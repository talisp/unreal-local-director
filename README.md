# unreal-local-director

> **Alpha 0.0.1 — broken, incomplete, far from usable.** Published early so others can see the approach, reproduce the failures and help. Expect rough edges everywhere.

**Goal:** let a **local LLM** drive **Unreal Engine 5** from simple, plain-language orders ("make the audience chat quietly", "measure if this character is standing", "film him from the side") and get back **verified results**, so we can produce **reference videos** for video models such as **MiniMax H3** and **LTX 2.5** (blocking, character motion, camera) without paying a frontier model for every click.

### Where this is going (the important part, not built yet)

The end state is **directing, not operating**. You say what you want, in plain words, and the scene happens:

- *"Make X do this"* → the character does it: pick the motion, apply it, check the pose, show you a frame.
- *"Build a little square where X can stroll with Y"* → the agent **builds the square** (layout, ground, benches, trees, lighting, from ready-made assets), places both characters, makes them walk together without colliding, frames the camera and records the reference clip.

Today we are only at the first rung: verified standing animations on existing characters. Building places, walking paths and multi-character staging are the **future and most important part** of the roadmap.

Frontier models (Claude Opus, GPT/Codex-class) can already operate Unreal reasonably well. They are also slow to iterate with and expensive per action. This project is the opposite bet: a **small, cheap, local model** plus **a thick layer of deterministic tools** that do the hard part, measure the result and refuse to lie.

---

## Why the official Unreal MCP is not enough (for a small local model)

Unreal 5.8 ships an official MCP server with **29 toolsets and ~593 atomic tools** (get/set properties, spawn actors, capture viewport, run editor scripts...). A frontier model can compose those. A local model could not:

| What we measured (859 real calls by our local agent) | Why it happens |
|---|---|
| **~15% of calls failed** | guessed property names (`ActorLabel` vs `actorLabel`), missing required params, the meta-tool wrapped inside itself |
| `execute_tool_script`: 503 calls, **19% errors** | the model writes editor Python on the fly, with the wrong API |
| "Done!" with the character **lying on the floor** | Unreal's bounding box does **not** follow the animated pose: a character lying down still "measures" 180 cm tall |
| Long hangs, editor modal dialogs, Play-In-Editor | one bad call blocks everything; the model has no way to know the state |

Atomic tools give the model **power without verification**. A small model needs the opposite: **few tools, each a whole task, each one measuring its own result**.

## What we built (the approach)

Borrowed from Blender agent projects (see *Credits*), re-engineered for Unreal:

| Layer | What it is | Who uses it |
|---|---|---|
| **Atomic** | the ~593 official MCP tools | only our macros, internally |
| **Macro** | one sentence = one tool: `aplicar_clipe(actor, clip)`, `medir_personagem(actor)`, `capturar_evidencia(actor)` — each reads back and **measures** | the local LLM |
| **Workflow** | bounded processes: `plateia_em_loop` (give a crowd idle/talk loops, one actor at a time, stop at first failure) | the local LLM |
| **Truth** | deterministic gates: standing, feet on the floor, actor didn't move, no neighbour collision, legs planted | every macro |
| **Vision** | second opinion on a captured frame — never approves alone | workflows |

Key pieces (all in `src/unreal_macros/`):

- **The "parallel studio"** (idea of the project owner): to measure a pose we **copy** the character into a neutral, closed grey room far from the scene, capture with and without the copy, and the pixel difference is the silhouette. A projected height ruler converts pixels to cm. The original is never touched. Studio v1 used the sky as background (cyan sky ≈ cyan mannequin, and it over-exposed); v2 is a closed **unlit grey room** with fixed exposure, and the measuring copy is painted **unlit white**:

  | v1 (sky) | v1 after editor changes | v2 (grey room) |
  |---|---|---|
  | ![v1](docs/img/studio_v1_sky.png) | ![v1 overexposed](docs/img/studio_v1_overexposed.png) | ![v2](docs/img/studio_v2_gray_room.png) |

- **Gates**: `silhueta_de_pe` (160–210 cm), `pes_no_chao` (±4 cm to the real floor), `pose_em_todo_clipe` (4 instants of the clip), `pes_plantados` (leg-mask IoU: walking scores 0.0, talking 0.7–0.8), `ator_parado`, `distancia_vizinhos`, `sem_oclusao_cenario`.
- **Every failure restores** the previous state and **checks** the restore. A single lock: one operator in Unreal at a time.
- **Escape hatch** `chamada_avancada`: read-only access to the atomic tools, logged.
- **Clip library search** (`buscar_clipe`, `previa_clipe`): text search + 3-frame previews over a local Mixamo-style library (not included).
- **Contract tests** (`tests/testes_contrato.py`): 22 cases including negative controls (walking, falling, kneeling, missing roll fix, glued neighbour, forbidden saves) that **must** fail.
- **Sandbox guard** (`sandbox_guard.py`): lets an agent experiment with code changes against Unreal while refusing saves, deletes, level changes, editor scripts and any non-test actor.

Docs (Portuguese, as written during the work): `docs/pt/` — tool policy, macro list, MCP inventory, the overnight agent benchmark analysis and an external review.

## The local model: Strata + Qwen

The runtime target is **Qwen3.8-Flash-Next** (UD-IQ4_XS quant) served by **Strata** on a single 48 GB GPU machine, driven by the **Hermes** agent. In our experience it is **far better suited** to this job than the dense **Qwen3.8 27B**, which was slow and quite limited for tool-heavy Unreal work: long waits per step and many more malformed calls.

An overnight benchmark (55+ attempts, every claim cross-checked against the real tool reports) showed the local agent is **honest** (222/224 numbers it logged matched the tool output) and good at finding bugs in *our* macros — but weak at obeying "stop" / "keep going" orders. Details: `docs/pt/ANALISE_BANCADA_2026-10-06.md`.

Frontier models were used to **build and review** this scaffolding, not to run it.

## Status (honest)

Works in our lab, barely:
- applying a standing loop (idle/talk/gesture) to a character with verified pose and feet;
- crowd idle loops one actor at a time;
- evidence frames; clip search and previews.

Broken / missing:
- **no walking, stairs, sitting or standing up** (no locomotion macro yet);
- Sequencer evaluation in the editor is blocked on our setup;
- pose by bone transforms needs an in-editor Python toolset (not installed yet);
- the first measurement in a new process can be unstable; many hard-coded assumptions (Y Bot skeleton, our level layout, Portuguese tool names);
- measurement is slow (~2,000 Unreal calls for the test suite).

## Requirements (if you want to try anyway)

- Unreal Engine 5.8 with the official MCP plugin listening on `http://127.0.0.1:8001/mcp`
- Python 3.11, `pip install -r requirements.txt`
- A level with Y Bot–style characters; a Mixamo-style FBX clip library (set `ULD_CLIP_LIBRARY`)
- `ULD_EVIDENCE_DIR` for captured frames
- Run the MCP server: `python src/server.py` (stdio), then point your agent (Hermes, or any MCP client) at it.

## Contributing

Issues and ideas welcome — especially: locomotion with collision gates, bone-based pose measurement, faster/stable capture, English tool names. A new macro is only accepted with **3/3 positive cases and a negative control that fails** (policy rule 11).

## Credits

See [NOTICE.md](NOTICE.md). Built by **Talis** (direction, the "parallel studio" idea, lab), with **Claude Code** (implementation) and **Codex "Astra"** (review); runtime agent **Hermes** on **Strata/Qwen**.

## License

Custom, source-available, **not open source** — see [LICENSE](LICENSE). This project draws on ideas from other projects and we have not yet cleared what can be fully opened.

---

### Resumo em português

Alfa inicial (quebrado) de uma camada de **macros verificadas** sobre o MCP oficial do Unreal 5.8, para que um **LLM local** (Hermes + Qwen3.8-Flash-Next no Strata) dirija cenas com ordens simples e receba resultados medidos, com o objetivo de gerar **vídeos de referência para MiniMax H3 e LTX 2.5**. O MCP oficial tem ~593 ferramentas atômicas: poder demais e verificação de menos para um modelo pequeno (15% de chamadas com erro na nossa medição; "pronto" com o boneco deitado, porque a caixa envolvente não acompanha a pose). Usamos como inspiração projetos de agentes para Blender (camadas atômica/macro/workflow, gates medidos) e fizemos a reengenharia para o Unreal, incluindo o "estúdio paralelo" para medir a pose pela silhueta. Andar, escada, sentar e Sequencer ainda não funcionam. **O objetivo final** é dirigir em linguagem natural: "faça X e o personagem faz"; "crie uma praça para X passear com Y" → o agente constrói a praça (assets prontos, piso, bancos, árvores, luz), posiciona os dois, faz os dois andarem sem colidir, enquadra a câmera e grava o vídeo de referência. Essa é a parte futura e mais importante. Documentação de trabalho em `docs/pt/`.
