# Batch 013 — DRAFTS for Ryan approval

**Status:** staged locally for human gate. Do **not** auto-publish.  
**Theme:** Appomattox 1865 — Grant’s terms decision (**ELO-015**).

Public packs only (`scenarios/public/`). No MANDOS master sources.

| File | Scenario | Cut | Platforms | Labels |
|------|----------|-----|-----------|--------|
| `ELO-015-historical.md` | Grant’s parole terms | historical | YT + TT | 📗 documented |
| `ELO-015-harsher_terms.md` | harder surrender sheet | simulated | YT + TT | 🧪 simulated |
| `ELO-015-delay_for_orders.md` | delay for political orders | dramatized | YT + TT | dramatized / 🧪 |

Postiz payload skeleton: `postiz-drafts.json` (`status: draft`, placeholder integration IDs).

## Render commands

```bash
export ANOR_MOCK_MEDIA=1
python3 -m pipeline.cli video --scenario ELO-015 --choice historical
python3 -m pipeline.cli video --scenario ELO-015 --choice harsher_terms
python3 -m pipeline.cli video --scenario ELO-015 --choice delay_for_orders
```

## Human gate

- [ ] Ryan reviews tone (no triumphal gore; no Lost Cause romance)
- [ ] On-screen 🧪 / dramatized labels for non-historical cuts
- [ ] Integration IDs filled after brand channels exist
- [ ] Ryan flips draft → schedule (never agents)
