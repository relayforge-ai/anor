# Batch 002 — DRAFTS for Ryan approval

**Status:** staged locally for human gate. Do **not** auto-publish.  
**Theme:** Cuban Missile Crisis — presidential EXCOMM decision (**ELO-007**), paired with batch-001’s submarine near-miss (**ELO-013**).

Public packs only (`scenarios/public/`). No MANDOS master sources.

| File | Scenario | Cut | Platforms | Labels |
|------|----------|-----|-----------|--------|
| `ELO-007-historical.md` | EXCOMM | historical quarantine | YT + TT | 📗 documented |
| `ELO-007-surgical_strike.md` | EXCOMM | airstrike first | YT + TT | 🧪 simulated |
| `ELO-007-invasion.md` | EXCOMM | full invasion | **YT only** | 🧪 simulated · sensitive |

Postiz payload skeleton: `postiz-drafts.json` (`status: draft`, placeholder integration IDs).

## Render commands

```bash
export ANOR_MOCK_MEDIA=1   # or set LLM_URL IMAGE_URL TTS_URL on Dawes
python3 -m pipeline.cli video --scenario ELO-007 --choice historical
python3 -m pipeline.cli video --scenario ELO-007 --choice surgical_strike
python3 -m pipeline.cli video --scenario ELO-007 --choice invasion
```

## Human gate

- [ ] Ryan reviews tone (no nuclear glamor, no “clean strike” certainty)
- [ ] Ryan confirms YT-only for invasion cut
- [ ] Integration IDs filled after brand channels exist
- [ ] Ryan flips draft → schedule (never agents)
