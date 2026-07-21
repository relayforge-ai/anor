# Batch 009 — DRAFTS for Ryan approval

**Status:** staged locally for human gate. Do **not** auto-publish.  
**Theme:** Gap fill — remaining public choice cuts not covered in batches 001–008  
(**ELO-013** surface delay, **ELO-001** Barbarossa forks, **ELO-003** recon).

Public packs only (`scenarios/public/`). No MANDOS master sources.

| File | Scenario | Cut | Platforms | Labels |
|------|----------|-----|-----------|--------|
| `ELO-013-surface_delay.md` | B-59 delay the vote | surface_delay | YT + TT | dramatized / 🧪 |
| `ELO-001-immediate_accept.md` | Barbarossa faster accept | immediate_accept | YT + TT | 🧪 simulated |
| `ELO-001-disinformation_trap.md` | longer denial framing | disinformation_trap | YT (+ careful TT) | 🧪 simulated |
| `ELO-003-recon.md` | Cannae limited probe | recon | YT + TT | 🧪 simulated |

Postiz payload skeleton: `postiz-drafts.json` (`status: draft`, placeholder integration IDs).

## Render commands

```bash
export ANOR_MOCK_MEDIA=1   # or set LLM_URL IMAGE_URL TTS_URL on Dawes
python3 -m pipeline.cli video --scenario ELO-013 --choice surface_delay
python3 -m pipeline.cli video --scenario ELO-001 --choice immediate_accept
python3 -m pipeline.cli video --scenario ELO-001 --choice disinformation_trap
python3 -m pipeline.cli video --scenario ELO-003 --choice recon
```

## Human gate

- [ ] Ryan reviews tone (no victory fantasy; no nuclear glamor on surface_delay companion context)
- [ ] On-screen 🧪 / dramatized labels required for all four cuts
- [ ] disinformation_trap: extra care if clipped out of context
- [ ] Integration IDs filled after brand channels exist
- [ ] Ryan flips draft → schedule (never agents)
