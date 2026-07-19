# DRAFT — ELO-009 air-heavy reduction (dramatized) — for approval

**Status:** DRAFT · do not publish  
**Platforms:** YouTube, TikTok (with 🧪 / dramatized labels)  
**Speculation:** DRAMATIZED process emphasis — not a secret alternate war plan  
**Pack:** `scenarios/public/ELO-009.json`

## YouTube title
DRAMATIZED: What if Dunkirk were left mostly to the Luftwaffe?

## YouTube description
⚠️ Dramatized / simulated process — not a second history book.

Documented baseline: the halt, the fight, and Dynamo under air attack.
This cut sharpens a real impulse in the debate: conserve armor, lean on air power to break the pocket and the port.

Bombs can kill docks and nerves. They do not automatically seal every beach. We label the emphasis so clips cannot pretend this is “what really happened instead.”

📗 Baseline = halt + mixed pressure · 🧪 this cut = dramatized air-heavy emphasis  
Companion: historical halt video; press-armor simulation.

#althistory #dunkirk #luftwaffe #ww2

## TikTok caption
What if the answer is mostly the air force?
Dramatized process — not “secret history.”
📗 Halt still happened in the real timeline.
#historytok #dunkirk #ww2

## Mandatory on-screen labels
- Cold open: 📗 DOCUMENTED baseline
- Fork card: 🧪 DRAMATIZED EMPHASIS
- End: “Not a claim of a clean air-only victory.”

## Render (offline-safe)
```bash
export ANOR_MOCK_MEDIA=1
python3 -m pipeline.cli video --scenario ELO-009 --choice luftwaffe_only
```
