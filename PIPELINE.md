# ANOR content pipeline

Interactive decision forks + narrated explainers for public ELOSTIRION packs,
plus the **Forked History** freemium product site (`webapp/`).

## Design rules

1. **Endpoints from env only** — `LLM_URL`, `IMAGE_URL`, `TTS_URL`. No hardcoded hosts.
2. **Public packs only** — `scenarios/public/`. Never MANDOS master sources.
3. **Label speculation** — `documented` | `dramatized` | `simulated` (never strip labels).
4. **Human-gate publishing** — `content/drafts/` only until Ryan approves. **Never** auto-publish to TikTok/YouTube.
5. **Sovereign-first** — local GPU (Dawes → Nauvoo/Ganymede) before paid APIs; flag cost if cloud.
6. **No secrets in repo** — copy `.env.example` → `.env` on the host only.

## Quick start

```bash
cd /path/to/anor
python3 -m pipeline.cli health
python3 -m pipeline.cli list

# Offline / CI (placeholders + silent TTS)
export ANOR_MOCK_MEDIA=1
python3 -m pipeline.cli fork --scenario ELO-003 --choice march --no-llm
python3 -m pipeline.cli video --scenario ELO-013 --choice historical
# One still (Comfy SDXL+ESRGAN when IMAGE_URL set; mock under ANOR_MOCK_MEDIA=1)
python3 -m pipeline.cli still --scenario ELO-013 --choice historical
python3 -m pipeline.cli still --prompt "1944 map table archival" --out still.png --ken-burns

# Product site — Forked History
python3 -m pipeline.cli site --port 8787
# open http://127.0.0.1:8787
```

## Public packs (current)

| ID | Title | Era | Decision |
|----|-------|-----|----------|
| ELO-003 | Hannibal after Cannae | 216 BC | March on Rome? |
| ELO-004 | Caesar at the Rubicon | 49 BC | Cross or stand down? |
| ELO-005 | July Crisis blank cheque | 1914 | Underwrite Vienna or restrain? |
| ELO-009 | Dunkirk halt | 1940 | Press armor or halt? |
| ELO-001 | Stalin's dacha, Barbarossa | 1941 | Accept invasion reports? |
| ELO-008 | Overlord D-Day go/no-go | 1944 | Weather window: go or delay? |
| ELO-006 | Berlin Blockade airlift | 1948 | Airlift vs force corridors? |
| ELO-010 | Bay of Pigs go/no-go | 1961 | Scrub, proceed, or denser air? |
| ELO-007 | EXCOMM quarantine | 1962 | Quarantine vs strike? |
| ELO-013 | Arkhipov on B-59 | 1962 | Nuclear torpedo vote? |

Authoritative table: [`scenarios/public/README.md`](scenarios/public/README.md). Schema: `scenarios/schema/fork_scenario.schema.json`.

## Dawes / Nauvoo env

```bash
# Example — Ollama OpenAI-compat on fleet host (never commit real hosts/secrets)
export LLM_URL=http://<fleet-host>:11434/v1
export LLM_MODEL=qwen2.5:32b

# ComfyUI on GPU box (Dawes: SDXL base + Real-ESRGAN 4×, serialized)
export IMAGE_URL=http://dawes:8188   # or http://192.168.4.27:8188
export IMAGE_MODEL=sd_xl_base_1.0.safetensors   # OpenRAIL — not Flux.1-dev
export IMAGE_BACKEND=comfy
# ANOR_COMFY_UPSCALE=1 ANOR_COMFY_UPSCALE_MODEL=RealESRGAN_x4plus.pth
# ANOR_STILL_WIDTH=1024 ANOR_STILL_HEIGHT=576
# ANOR_VIDEO_WIDTH=1920 ANOR_VIDEO_HEIGHT=1080

# Local TTS bridge (OpenAI-compatible speech)
export TTS_URL=http://<fleet-host>:8880/v1
export TTS_MODEL=tts-1

# Optional keys if the bridge requires them
export LLM_API_KEY=...
export IMAGE_API_KEY=...
export TTS_API_KEY=...

# Outage safety nets (default on) — still prefer live endpoints when healthy
# ANOR_IMAGE_FALLBACK_MOCK=1
# ANOR_TTS_FALLBACK_MOCK=1
```

Same code path moves Dawes → Nauvoo/Ganymede by changing env only. Docker: see [`DEPLOY.md`](DEPLOY.md).

## Layout

```
anor/
├── scenarios/public/     # shareable decision packs
├── scenarios/schema/     # fork_scenario.schema.json
├── pipeline/             # clients, fork engine, video, CLI
├── webapp/               # Forked History product site (stdlib HTTP SPA)
├── content/drafts/       # social captions staged for Ryan (batch-001+)
├── outputs/              # local renders (gitignored)
├── Dockerfile            # portable site image (non-root)
├── docker-compose.yml
├── DEPLOY.md
├── sim/                  # industrial decision-tree sim engine (separate)
└── PIPELINE.md           # this file
```

## Social drafts (human gate)

| Batch | Theme | Status |
|-------|--------|--------|
| `content/drafts/batch-001/` | Cannae, Arkhipov, Barbarossa | DRAFT |
| `content/drafts/batch-002/` | EXCOMM (ELO-007) | DRAFT |
| `content/drafts/batch-003/` | Dunkirk (ELO-009) | DRAFT |
| `content/drafts/batch-004/` | Rubicon (ELO-004) | DRAFT |
| `content/drafts/batch-005/` | July Crisis blank cheque (ELO-005) | DRAFT |
| `content/drafts/batch-006/` | Berlin Airlift (ELO-006) | DRAFT |
| `content/drafts/batch-007/` | Overlord D-Day go/no-go (ELO-008) | DRAFT |
| `content/drafts/batch-008/` | Bay of Pigs (ELO-010) | DRAFT |

Each batch has markdown captions + `postiz-drafts.json` with `status: "draft"` and placeholder integration IDs. **Agents must not publish.**

## Cost flags

| Path | Cost |
|------|------|
| `ANOR_MOCK_MEDIA=1` | $0 |
| Local Ollama + Comfy + system/`say` TTS | watts only |
| Cloud LLM/image/TTS via paid `*_URL` | **flag before use** — not default |

## Tests

```bash
# Offline unit surface (CI mirrors this set)
export ANOR_MOCK_MEDIA=1
python3 -m unittest \
  pipeline.tests.test_pipeline \
  pipeline.tests.test_image_client \
  pipeline.tests.test_tts_client \
  pipeline.tests.test_validate \
  webapp.tests.test_webapp \
  webapp.tests.test_security \
  scripts.tests.test_deploy_config \
  scripts.tests.test_social_drafts \
  scripts.tests.test_pipeline_docs \
  -v
```
