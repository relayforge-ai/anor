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

## Batch 001 — three pilots

| File | Scenario | Cut | Platforms |
|------|----------|-----|-----------|
| `batch-001/ELO-003-historical.md` | Cannae | historical | YT + TT |
| `batch-001/ELO-003-march.md` | Cannae | counterfactual (labeled) | YT + TT |
| `batch-001/ELO-013-historical.md` | Arkhipov | historical | YT + TT |
| `batch-001/ELO-013-launch.md` | Arkhipov | nightmare branch (labeled) | YT only (sensitive) |
| `batch-001/ELO-001-historical.md` | Barbarossa night | historical | YT + TT |

Render commands (offline-safe with mock media, or point env at Dawes):

```bash
export ANOR_MOCK_MEDIA=1   # or set LLM_URL IMAGE_URL TTS_URL
python -m pipeline.cli video --scenario ELO-003 --choice historical
python -m pipeline.cli video --scenario ELO-003 --choice march
python -m pipeline.cli video --scenario ELO-013 --choice historical
```

## Human gate checklist

- [ ] Ryan approves channel names / avatars
- [ ] Ryan connects TikTok + YouTube in Postiz (or native Studio)
- [ ] Ryan reviews each draft caption for tone
- [ ] Ryan flips draft → schedule (never auto-publish from agents)
