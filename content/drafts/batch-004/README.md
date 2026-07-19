# Batch 004 — DRAFTS for Ryan approval

**Status:** staged locally for human gate. Do **not** auto-publish.  
**Theme:** Caesar at the Rubicon, 49 BC (**ELO-004**).

Public packs only (`scenarios/public/`). No MANDOS master sources.

| File | Scenario | Cut | Platforms | Labels |
|------|----------|-----|-----------|--------|
| `ELO-004-historical.md` | Rubicon | historical crossing | YT + TT | 📗 documented |
| `ELO-004-stand_down.md` | Rubicon | stand down | YT + TT | 🧪 simulated |
| `ELO-004-negotiate_delay.md` | Rubicon | negotiate delay | YT + TT | dramatized / 🧪 |

Postiz payload skeleton: `postiz-drafts.json` (`status: draft`, placeholder integration IDs).

## Render commands

```bash
export ANOR_MOCK_MEDIA=1   # or set LLM_URL IMAGE_URL TTS_URL on Dawes
python3 -m pipeline.cli video --scenario ELO-004 --choice historical
python3 -m pipeline.cli video --scenario ELO-004 --choice stand_down
python3 -m pipeline.cli video --scenario ELO-004 --choice negotiate_delay
```

## Human gate

- [ ] Ryan reviews tone (no destiny-meme glamor; no tidy “Republic saved” ending)
- [ ] On-screen 🧪 / dramatized labels required for non-historical cuts
- [ ] Integration IDs filled after brand channels exist
- [ ] Ryan flips draft → schedule (never agents)
