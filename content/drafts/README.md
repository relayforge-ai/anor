# First content batch — DRAFTS for Ryan approval

**Status:** staged locally for human gate. Do **not** auto-publish.

These captions and scripts are built only from public ELOSTIRION decision packs
in `scenarios/public/`. No MANDOS master sources.

## Channels (needs Ryan)

Creating TikTok and YouTube brand accounts requires human identity/verification.
This batch prepares the creative + Postiz draft payloads once integrations exist.

Suggested channel names (for Ryan to claim):

| Platform | Suggested handle / title | Notes |
|----------|--------------------------|--------|
| YouTube  | **Forked History** or **ANOR Fork** | Long-form 8–15 min + Shorts |
| TikTok   | **@forkedhistory** or **@anorfork** | 45–90s decision cold-opens |

Brand line: *Real decision points. Labeled speculation. Receipts on screen.*

## Batch 001 — pilots

| File | Scenario | Cut | Platforms |
|------|----------|-----|-----------|
| `batch-001/ELO-003-historical.md` | Cannae | historical | YT + TT |
| `batch-001/ELO-003-march.md` | Cannae | counterfactual (labeled) | YT + TT |
| `batch-001/ELO-013-historical.md` | Arkhipov | historical | YT + TT |
| `batch-001/ELO-013-launch.md` | Arkhipov | nightmare branch (labeled) | YT only (sensitive) |
| `batch-001/ELO-001-historical.md` | Barbarossa night | historical | YT + TT |

## Batch 002 — EXCOMM (ELO-007)

| File | Scenario | Cut | Platforms |
|------|----------|-----|-----------|
| `batch-002/ELO-007-historical.md` | EXCOMM quarantine | historical | YT + TT |
| `batch-002/ELO-007-surgical_strike.md` | airstrike first | simulated | YT + TT |
| `batch-002/ELO-007-invasion.md` | full invasion | simulated · sensitive | YT only |

See `batch-002/README.md` and `batch-002/postiz-drafts.json`.

## Batch 003 — Dunkirk (ELO-009)

| File | Scenario | Cut | Platforms |
|------|----------|-----|-----------|
| `batch-003/ELO-009-historical.md` | Dunkirk halt | historical | YT + TT |
| `batch-003/ELO-009-press_armor.md` | press armor | simulated | YT + TT |
| `batch-003/ELO-009-luftwaffe_only.md` | air-heavy | dramatized | YT + TT |

See `batch-003/README.md` and `batch-003/postiz-drafts.json`.

## Batch 004 — Rubicon (ELO-004)

| File | Scenario | Cut | Platforms |
|------|----------|-----|-----------|
| `batch-004/ELO-004-historical.md` | Rubicon crossing | historical | YT + TT |
| `batch-004/ELO-004-stand_down.md` | stand down | simulated | YT + TT |
| `batch-004/ELO-004-negotiate_delay.md` | negotiate delay | dramatized | YT + TT |

See `batch-004/README.md` and `batch-004/postiz-drafts.json`.

Render commands (offline-safe with mock media, or point env at Dawes):

```bash
export ANOR_MOCK_MEDIA=1   # or set LLM_URL IMAGE_URL TTS_URL
python -m pipeline.cli video --scenario ELO-003 --choice historical
python -m pipeline.cli video --scenario ELO-003 --choice march
python -m pipeline.cli video --scenario ELO-013 --choice historical
python -m pipeline.cli video --scenario ELO-007 --choice historical
python -m pipeline.cli video --scenario ELO-007 --choice surgical_strike
python -m pipeline.cli video --scenario ELO-009 --choice historical
python -m pipeline.cli video --scenario ELO-009 --choice press_armor
python -m pipeline.cli video --scenario ELO-004 --choice historical
python -m pipeline.cli video --scenario ELO-004 --choice stand_down
```

## Human gate checklist

- [ ] Ryan approves channel names / avatars
- [ ] Ryan connects TikTok + YouTube in Postiz (or native Studio)
- [ ] Ryan reviews each draft caption for tone
- [ ] Ryan flips draft → schedule (never auto-publish from agents)
