# ANOR goal — ship report (Grok · Io · 2026-07-18)

## Assessment (start)

| Layer | State |
|-------|--------|
| ANOR industrial scenarios (001–007) | Complete in MANDOS working tree (screenplays + maps). **Not** re-authored. Master sources remain INTERNAL. |
| ELOSTIRION library (001–021) | Complete + adversarial review. Public product surface = decision packs, not full internal harness dumps. |
| Public `relayforge-ai/anor` | Had sim engine + CI only. **No** content pipeline, **no** public packs, **no** social drafts. |
| Notion Studio Build Doc | Confirmed: scenarios done; build pipeline/site/socials from finished canon. |

## What shipped (this session)

### In public `anor` repo

1. **Public decision packs** (`scenarios/public/`)
   - `ELO-003` Cannae · `ELO-013` Arkhipov · `ELO-001` Barbarossa night
   - Schema + README · speculation levels · sources · provenance notes
2. **Pipeline** (`pipeline/`)
   - Env endpoints: `LLM_URL`, `IMAGE_URL`, `TTS_URL` (no hardcoded hosts)
   - Interactive fork site (`python -m pipeline.cli site`)
   - Video path: script → TTS → stills → ffmpeg Ken Burns
   - CLI: `health` / `list` / `fork` / `video` / `site` / `show`
   - Offline mock path via `ANOR_MOCK_MEDIA=1`
3. **Docs**: `PIPELINE.md`, `.env.example`, README updates, CI job for pipeline tests
4. **Social drafts** (`content/drafts/batch-001/`)
   - Captions + titles for YT/TT · sensitive launch branch gated
   - `postiz-drafts.json` template · `POSTIZ_STATUS.md`

### Verified on Io

- 8/8 pipeline unit tests pass (offline)
- 3 draft MP4s rendered under `outputs/videos/` (mock stills; real ffmpeg mux)
- Live LLM fork against local Ollama (`LLM_URL=http://127.0.0.1:11434/v1`, mistral-nemo) succeeded
- Notion blackboard checkpoint filed
- Postiz auth OK — integrations listed (see needs Ryan)

### Guardrails honored

- No MANDOS master sources published or committed
- Work only in public `anor`
- No auto-publish
- No secrets in repo
- Speculation labeled on counterfactual branches

## Needs Ryan

1. **Channels** — create dedicated YouTube (*Forked History* / *ANOR Fork*) and TikTok (`@forkedhistory`). Existing Postiz YT/TT integrations are **wrong brand** (Telchar, CCI, sheldon.clawd). Agent deliberately did **not** draft-post onto them.
2. **Connect** new channels in Postiz; then run draft create from `content/drafts/batch-001/`.
3. **Approve** captions in `batch-001/*.md` (especially ELO-013 launch sensitivity).
4. **GPU polish** — point `IMAGE_URL` / `TTS_URL` at Dawes Comfy + TTS for non-placeholder stills/voice; re-render batch.
5. **Optional** — expand public packs beyond 001/003/013; brand assets (avatar, banner).
6. **Do not** publish industrial ANOR-00x incident content as entertainment without a separate legal/ethics pass (CSB-derived).

## How to run (Dawes → Nauvoo)

```bash
export LLM_URL=http://<host>:11434/v1
export LLM_MODEL=qwen2.5:32b
export IMAGE_URL=http://<host>:8188
export TTS_URL=http://<host>:8880/v1   # or leave unset for system say
python3 -m pipeline.cli site --port 8787
python3 -m pipeline.cli video --scenario ELO-003 --choice historical
```

Same code; change env only.
