# ANOR content pipeline

Interactive decision forks + narrated explainers for public ELOSTIRION packs.

## Design rules

1. **Endpoints from env only** — `LLM_URL`, `IMAGE_URL`, `TTS_URL`. No hardcoded hosts.
2. **Public packs only** — `scenarios/public/`. Never MANDOS master sources.
3. **Label speculation** — `documented` | `dramatized` | `simulated`.
4. **Human-gate publishing** — drafts only until Ryan approves.
5. **Sovereign-first** — local GPU (Dawes → Nauvoo) before paid APIs; flag cost if cloud.

## Quick start

```bash
cd /path/to/anor
python3 -m pipeline.cli health
python3 -m pipeline.cli list

# Offline / CI (placeholders + system or silent TTS)
export ANOR_MOCK_MEDIA=1
python3 -m pipeline.cli fork --scenario ELO-003 --choice march --no-llm
python3 -m pipeline.cli video --scenario ELO-013 --choice historical

# Interactive site
python3 -m pipeline.cli site --port 8787
# open http://127.0.0.1:8787
```

## Dawes / Nauvoo env

```bash
# Example — Ollama OpenAI-compat on fleet host
export LLM_URL=http://<dawes-or-nauvoo>:11434/v1
export LLM_MODEL=qwen2.5:32b

# ComfyUI on GPU box
export IMAGE_URL=http://<dawes-or-nauvoo>:8188
export IMAGE_MODEL=v1-5-pruned-emaonly.safetensors
export IMAGE_BACKEND=comfy

# Local TTS bridge (OpenAI-compatible speech)
export TTS_URL=http://<dawes-or-nauvoo>:8880/v1
export TTS_MODEL=tts-1

# Optional keys if the bridge requires them
export LLM_API_KEY=...
export IMAGE_API_KEY=...
export TTS_API_KEY=...
```

Same code path moves from Dawes → Nauvoo by changing env only.

## Layout

```
anor/
├── scenarios/public/     # shareable decision packs
├── scenarios/schema/     # fork_scenario.schema.json
├── pipeline/             # clients, fork engine, video, site
├── content/drafts/       # social captions staged for Ryan
├── outputs/              # local renders (gitignored)
├── sim/                  # existing decision-tree sim engine
└── PIPELINE.md           # this file
```

## Cost flags

| Path | Cost |
|------|------|
| `ANOR_MOCK_MEDIA=1` | $0 |
| Local Ollama + Comfy + system/`say` TTS | watts only |
| Cloud LLM/image/TTS via paid `*_URL` | **flag before use** — not default |

## Tests

```bash
python3 -m pipeline.tests.test_pipeline
# or
python3 -m unittest pipeline.tests.test_pipeline -v
```
