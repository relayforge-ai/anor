# Batch 011 — DRAFTS for Ryan approval

**Status:** staged locally for human gate. Do **not** auto-publish.  
**Theme:** Waterloo 1815 — commit the Guard or break contact (**ELO-012**).

Public packs only (`scenarios/public/`). No MANDOS master sources.

| File | Scenario | Cut | Platforms | Labels |
|------|----------|-----|-----------|--------|
| `ELO-012-historical.md` | late Guard assault | historical | YT + TT | 📗 documented |
| `ELO-012-break_contact.md` | ordered disengagement | simulated | YT + TT | 🧪 simulated |
| `ELO-012-commit_early.md` | earlier Guard | dramatized | YT + TT | dramatized / 🧪 |

Postiz payload skeleton: `postiz-drafts.json` (`status: draft`, placeholder integration IDs).

## Render commands

```bash
export ANOR_MOCK_MEDIA=1
python3 -m pipeline.cli video --scenario ELO-012 --choice historical
python3 -m pipeline.cli video --scenario ELO-012 --choice break_contact
python3 -m pipeline.cli video --scenario ELO-012 --choice commit_early
```

## Human gate

- [ ] Ryan reviews tone (no glory montage; no guaranteed victory fantasy)
- [ ] On-screen 🧪 / dramatized labels for non-historical cuts
- [ ] Integration IDs filled after brand channels exist
- [ ] Ryan flips draft → schedule (never agents)
