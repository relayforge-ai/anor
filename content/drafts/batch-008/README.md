# Batch 008 — DRAFTS for Ryan approval

**Status:** staged locally for human gate. Do **not** auto-publish.  
**Theme:** Bay of Pigs go/no-go, April 1961 (**ELO-010**).

Public packs only (`scenarios/public/`). No MANDOS master sources.

| File | Scenario | Cut | Platforms | Labels |
|------|----------|-----|-----------|--------|
| `ELO-010-historical.md` | Proceed limited air | historical | YT + TT | 📗 documented |
| `ELO-010-scrub.md` | Cancel before beach | simulated | YT + TT | 🧪 simulated |
| `ELO-010-dense_air.md` | Denser air cover | dramatized | YT + TT | dramatized / 🧪 |

Postiz payload skeleton: `postiz-drafts.json` (`status: draft`, placeholder integration IDs).

## Render commands

```bash
export ANOR_MOCK_MEDIA=1   # or set LLM_URL IMAGE_URL TTS_URL on Dawes
python3 -m pipeline.cli video --scenario ELO-010 --choice historical
python3 -m pipeline.cli video --scenario ELO-010 --choice scrub
python3 -m pipeline.cli video --scenario ELO-010 --choice dense_air
```

## Human gate

- [ ] Ryan reviews tone (no sanitized victory fantasy; no “easy scrub” certainty)
- [ ] On-screen 🧪 / dramatized labels required for non-historical cuts
- [ ] Integration IDs filled after brand channels exist
- [ ] Ryan flips draft → schedule (never agents)
