# Notice and credits

## Ideas and architecture we learned from (no code copied)
- **[PatrykIti/blender-ai-mcp](https://github.com/PatrykIti/blender-ai-mcp)** — goal-first routing, curated tool layers (atomic → macro → workflow), deterministic verification, vision as a second opinion. Our `docs/pt/POLITICA_FERRAMENTAS.md` adapts its tool-layering policy to Unreal.
- **[elithril/blender-kiln](https://github.com/elithril/blender-kiln)** — measured gates in an agent pipeline.

These are **Blender** projects (Python `bpy`). Nothing in them runs in Unreal: we re-engineered the ideas on top of the Unreal MCP (HTTP JSON-RPC), Unreal properties, viewport capture and our own image-based measurement.

## Platforms and tools used (not included)
- **Unreal Engine 5.8** and its official **MCP** plugin (Epic Games).
- **Hermes** agent (runtime), **Strata** serving **Qwen3.8-Flash-Next** (local model).
- **Mixamo**-style characters and animation clips (Adobe) — not redistributed.
- Python libraries: `mcp`, `numpy`, `Pillow`, `jsonschema`, `imageio-ffmpeg`.

## Studied for the v0.0.3 plan (no code copied yet)
- **[ezesubu/VERA](https://github.com/ezesubu/VERA)** (MIT, © 2026 EazyLabs / maVERAick), commit `8eeb1e7` — planned source of adapted code (isolated actor capture, retargeting, scene mood). When code is adapted, its license and per-file attribution will be added under `third_party/`.
- **[oliver-io/unreal-harness](https://github.com/oliver-io/unreal-harness)** (MIT, © 2026 Oliver Carrillo), commit `09a6bba` — gates, dry-run, closed error taxonomy, progressive disclosure, real-editor tests with a coverage oracle.
- **[Aethyr](https://aethyr.gg)** by Doug Fessler — ideas only: preview ops, batch rollback, backup ring, read-only mode and auditor.
- **[unrealcv/unrealcv](https://github.com/unrealcv/unrealcv)** (MIT) — reference for object masks and bone readout.

## People and agents
- **Talis** — project owner, direction, the "parallel studio" measurement idea.
- **Claude Code** (Anthropic) — implementation, tests, analysis.
- **Codex "Astra"** (OpenAI) — external code review.
