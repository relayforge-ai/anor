# Batch 014 — DRAFTS for Ryan approval

**Status:** staged locally for human gate. Do **not** auto-publish.  
**Theme:** Midway 1942 — carrier ambush decision (**ELO-016**).

Public packs only (`scenarios/public/`). No MANDOS master sources.

| File | Scenario | Cut | Platforms | Labels |
|------|----------|-----|-----------|--------|
| `ELO-016-historical.md` | spring the ambush | historical | YT + TT | 📗 documented |
| `ELO-016-wait_confirm.md` | wait for confirmation | simulated | YT + TT | 🧪 simulated |
| `ELO-016-disperse.md` | disperse carriers | dramatized | YT + TT | dramatized / 🧪 |

Postiz payload skeleton: `postiz-drafts.json` (`status: draft`, placeholder integration IDs).

## Render commands

```bash
export ANOR_MOCK_MEDIA=1
python3 -m pipeline.cli video --scenario ELO-016 --choice historical
python3 -m pipeline.cli video --scenario ELO-016 --choice wait_confirm
python3 -m pipeline.cli video --scenario ELO-016 --choice disperse
```

## Human gate

- [ ] Ryan reviews tone (no triumphal gore; no anime carrier fantasy)
- [ ] On-screen 🧪 / dramatized labels for non-historical cuts
- [ ] Integration IDs filled after brand channels exist
- [ ] Ryan flips draft → schedule (never agents)
