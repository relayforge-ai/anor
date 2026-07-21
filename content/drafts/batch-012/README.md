# Batch 012 — DRAFTS for Ryan approval

**Status:** staged locally for human gate. Do **not** auto-publish.  
**Theme:** Gettysburg 1863 — Pickett’s Charge decision (**ELO-014**).

Public packs only (`scenarios/public/`). No MANDOS master sources.

| File | Scenario | Cut | Platforms | Labels |
|------|----------|-----|-----------|--------|
| `ELO-014-historical.md` | center assault ordered | historical | YT + TT | 📗 documented |
| `ELO-014-refuse_charge.md` | refuse frontal assault | simulated | YT + TT | 🧪 simulated |
| `ELO-014-wide_turn.md` | wide turning movement | dramatized | YT + TT | dramatized / 🧪 |

Postiz payload skeleton: `postiz-drafts.json` (`status: draft`, placeholder integration IDs).

## Render commands

```bash
export ANOR_MOCK_MEDIA=1
python3 -m pipeline.cli video --scenario ELO-014 --choice historical
python3 -m pipeline.cli video --scenario ELO-014 --choice refuse_charge
python3 -m pipeline.cli video --scenario ELO-014 --choice wide_turn
```

## Human gate

- [ ] Ryan reviews tone (no glory montage; no Lost Cause fantasy)
- [ ] On-screen 🧪 / dramatized labels for non-historical cuts
- [ ] Integration IDs filled after brand channels exist
- [ ] Ryan flips draft → schedule (never agents)
