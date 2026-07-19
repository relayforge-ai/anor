# Batch 003 — DRAFTS for Ryan approval

**Status:** staged locally for human gate. Do **not** auto-publish.  
**Theme:** Dunkirk 1940 — German halt order (**ELO-009**).

Public packs only (`scenarios/public/`). No MANDOS master sources.

| File | Scenario | Cut | Platforms | Labels |
|------|----------|-----|-----------|--------|
| `ELO-009-historical.md` | Dunkirk | historical halt | YT + TT | 📗 documented |
| `ELO-009-press_armor.md` | Dunkirk | press armor | YT + TT | 🧪 simulated |
| `ELO-009-luftwaffe_only.md` | Dunkirk | air-heavy emphasis | YT + TT | dramatized / 🧪 |

Postiz payload skeleton: `postiz-drafts.json` (`status: draft`, placeholder integration IDs).

## Render commands

```bash
export ANOR_MOCK_MEDIA=1   # or set LLM_URL IMAGE_URL TTS_URL on Dawes
python3 -m pipeline.cli video --scenario ELO-009 --choice historical
python3 -m pipeline.cli video --scenario ELO-009 --choice press_armor
python3 -m pipeline.cli video --scenario ELO-009 --choice luftwaffe_only
```

## Human gate

- [ ] Ryan reviews tone (no “miracle” glamor; no clean panzer scoreboard)
- [ ] On-screen 🧪 / dramatized labels required for non-historical cuts
- [ ] Integration IDs filled after brand channels exist
- [ ] Ryan flips draft → schedule (never agents)
