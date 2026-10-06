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

## People and agents
- **Talis** — project owner, direction, the "parallel studio" measurement idea.
- **Claude Code** (Anthropic) — implementation, tests, analysis.
- **Codex "Astra"** (OpenAI) — external code review.
