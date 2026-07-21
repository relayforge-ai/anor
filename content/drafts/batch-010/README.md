# Batch 010 — DRAFTS for Ryan approval

**Status:** staged locally for human gate. Do **not** auto-publish.  
**Theme:** Munich 1938 — stand firm or concede the Sudetenland (**ELO-011**).

Public packs only (`scenarios/public/`). No MANDOS master sources.

| File | Scenario | Cut | Platforms | Labels |
|------|----------|-----|-----------|--------|
| `ELO-011-historical.md` | Munich settlement | historical | YT + TT | 📗 documented |
| `ELO-011-stand_firm.md` | stand firm behind Prague | simulated | YT + TT | 🧪 simulated |
| `ELO-011-limited_deal.md` | limited deal + delay | dramatized | YT + TT | dramatized / 🧪 |

Postiz payload skeleton: `postiz-drafts.json` (`status: draft`, placeholder integration IDs).

## Render commands

```bash
export ANOR_MOCK_MEDIA=1   # or set LLM_URL IMAGE_URL TTS_URL on Dawes
python3 -m pipeline.cli video --scenario ELO-011 --choice historical
python3 -m pipeline.cli video --scenario ELO-011 --choice stand_firm
python3 -m pipeline.cli video --scenario ELO-011 --choice limited_deal
```

## Human gate

- [ ] Ryan reviews tone (no cartoon cowardice; no guaranteed victory fantasy on stand_firm)
- [ ] On-screen 🧪 / dramatized labels required for non-historical cuts
- [ ] Integration IDs filled after brand channels exist
- [ ] Ryan flips draft → schedule (never agents)
