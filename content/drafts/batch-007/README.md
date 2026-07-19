# Batch 007 — DRAFTS for Ryan approval

**Status:** staged locally for human gate. Do **not** auto-publish.  
**Theme:** Overlord D-Day go/no-go, June 1944 (**ELO-008**).

Public packs only (`scenarios/public/`). No MANDOS master sources.

| File | Scenario | Cut | Platforms | Labels |
|------|----------|-----|-----------|--------|
| `ELO-008-historical.md` | Go for 6 June | historical | YT + TT | 📗 documented |
| `ELO-008-delay_longer.md` | Wait for cleaner weather | simulated | YT + TT | 🧪 simulated |
| `ELO-008-postpone_month.md` | Full tidal-cycle slip | dramatized | YT + TT | dramatized / 🧪 |

Postiz payload skeleton: `postiz-drafts.json` (`status: draft`, placeholder integration IDs).

## Render commands

```bash
export ANOR_MOCK_MEDIA=1   # or set LLM_URL IMAGE_URL TTS_URL on Dawes
python3 -m pipeline.cli video --scenario ELO-008 --choice historical
python3 -m pipeline.cli video --scenario ELO-008 --choice delay_longer
python3 -m pipeline.cli video --scenario ELO-008 --choice postpone_month
```

## Human gate

- [ ] Ryan reviews tone (no sanitized triumph montage; no “easy delay” certainty)
- [ ] On-screen 🧪 / dramatized labels required for non-historical cuts
- [ ] Integration IDs filled after brand channels exist
- [ ] Ryan flips draft → schedule (never agents)
