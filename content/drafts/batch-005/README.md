# Batch 005 — DRAFTS for Ryan approval

**Status:** staged locally for human gate. Do **not** auto-publish.  
**Theme:** July Crisis 1914 — blank cheque (**ELO-005**).

Public packs only (`scenarios/public/`). No MANDOS master sources.

| File | Scenario | Cut | Platforms | Labels |
|------|----------|-----|-----------|--------|
| `ELO-005-historical.md` | Blank cheque | historical | YT + TT | 📗 documented |
| `ELO-005-restrain.md` | Restrain Vienna | simulated | YT + TT | 🧪 simulated |
| `ELO-005-localize_only.md` | Localization gamble | dramatized | YT + TT | dramatized / 🧪 |

Postiz payload skeleton: `postiz-drafts.json` (`status: draft`, placeholder integration IDs).

## Render commands

```bash
export ANOR_MOCK_MEDIA=1   # or set LLM_URL IMAGE_URL TTS_URL on Dawes
python3 -m pipeline.cli video --scenario ELO-005 --choice historical
python3 -m pipeline.cli video --scenario ELO-005 --choice restrain
python3 -m pipeline.cli video --scenario ELO-005 --choice localize_only
```

## Human gate

- [ ] Ryan reviews tone (no single-cause war meme; no tidy “peace if only” certainty)
- [ ] On-screen 🧪 / dramatized labels required for non-historical cuts
- [ ] Integration IDs filled after brand channels exist
- [ ] Ryan flips draft → schedule (never agents)
