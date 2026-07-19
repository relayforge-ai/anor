# Batch 006 — DRAFTS for Ryan approval

**Status:** staged locally for human gate. Do **not** auto-publish.  
**Theme:** Berlin Blockade / Airlift 1948 (**ELO-006**).

Public packs only (`scenarios/public/`). No MANDOS master sources.

| File | Scenario | Cut | Platforms | Labels |
|------|----------|-----|-----------|--------|
| `ELO-006-historical.md` | Airlift | historical | YT + TT | 📗 documented |
| `ELO-006-force_corridors.md` | Force land corridors | simulated | YT + TT | 🧪 simulated |
| `ELO-006-negotiate_withdraw.md` | Bargain under blockade | dramatized | YT + TT | dramatized / 🧪 |

Postiz payload skeleton: `postiz-drafts.json` (`status: draft`, placeholder integration IDs).

## Render commands

```bash
export ANOR_MOCK_MEDIA=1   # or set LLM_URL IMAGE_URL TTS_URL on Dawes
python3 -m pipeline.cli video --scenario ELO-006 --choice historical
python3 -m pipeline.cli video --scenario ELO-006 --choice force_corridors
python3 -m pipeline.cli video --scenario ELO-006 --choice negotiate_withdraw
```

## Human gate

- [ ] Ryan reviews tone (no glamor of armored “easy” solutions; no nuclear shock-meme)
- [ ] On-screen 🧪 / dramatized labels required for non-historical cuts
- [ ] Integration IDs filled after brand channels exist
- [ ] Ryan flips draft → schedule (never agents)
