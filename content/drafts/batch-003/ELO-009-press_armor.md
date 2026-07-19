# DRAFT — ELO-009 press armor (counterfactual) — for approval

**Status:** DRAFT · do not publish  
**Platforms:** YouTube, TikTok (only with hard 🧪 labels)  
**Speculation:** SIMULATED branch — must stay labeled on-screen  
**Pack:** `scenarios/public/ELO-009.json`

## YouTube title
SPECULATION: What if German armor never halted at Dunkirk?

## YouTube description
⚠️ This video’s middle act is labeled SIMULATION — not history.

Documented fact: German armored thrusts **paused** during the critical days of the pocket.
Famous counterfactual: keep driving into the perimeter without that halt.

We hold the baseline honest, then fork. Canal country. Worn tanks. Fuel. A perimeter that still fights. Any “total capture on a timetable” certainty is overreach — we mark it 🧪 simulated.

**Provenance:** 📗 halt is documented · 🧪 press path is simulated  
Sources: operational histories of Flanders 1940; halt-order scholarship (public).

If you want the historical episode, watch the companion halt draft.

#althistory #dunkirk #ww2 #speculationlabeled

## TikTok caption
What if the panzers don’t stop?
We label this 🧪 SIMULATED. History records a halt.
Canal country ≠ clean map arrow.
#althistory #historytok #dunkirk

## Mandatory on-screen labels
- Cold open: 📗 DOCUMENTED (halt happened; Dynamo followed)
- Fork title card: 🧪 SIMULATED COUNTERFACTUAL
- End card: “Baseline unchanged: armor halted short of an instant finish.”

## Render (offline-safe)
```bash
export ANOR_MOCK_MEDIA=1
python3 -m pipeline.cli video --scenario ELO-009 --choice press_armor
```
