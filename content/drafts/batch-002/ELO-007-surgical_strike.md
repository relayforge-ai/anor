# DRAFT — ELO-007 surgical strike (counterfactual) — for approval

**Status:** DRAFT · do not publish  
**Platforms:** YouTube, TikTok (only with hard 🧪 labels)  
**Speculation:** SIMULATED branch — must stay labeled on-screen  
**Pack:** `scenarios/public/ELO-007.json`

## YouTube title
SPECULATION: What if the U.S. struck the Cuba missile sites first?

## YouTube description
⚠️ This video’s middle act is labeled SIMULATION — not history.

Documented fact: Kennedy opened with a **naval quarantine**, not an immediate airstrike.
Famous counterfactual: destroy the sites from the air on day one.

We hold the baseline honest, then fork. Incomplete intelligence. Possible surviving missiles. Soviet personnel on the island. Any “clean surgical fix” certainty is overreach — we mark it 🧪 simulated.

**Provenance:** 📗 quarantine is documented · 🧪 strike path is simulated  
Sources: EXCOMM debate literature; standard crisis chronology (public).

If you want the historical episode, watch the companion quarantine draft.

#althistory #cubanmissilecrisis #speculationlabeled #coldwar

## TikTok caption
What if EXCOMM says STRIKE first?
We label this 🧪 SIMULATED. History chose quarantine.
Incomplete intel ≠ clean win.
#althistory #historytok #coldwar

## Mandatory on-screen labels
- Cold open: 📗 DOCUMENTED (missiles real; quarantine was the choice)
- Fork title card: 🧪 SIMULATED COUNTERFACTUAL
- End card: “Baseline unchanged: the opening move was quarantine.”

## Render (offline-safe)
```bash
export ANOR_MOCK_MEDIA=1
python3 -m pipeline.cli video --scenario ELO-007 --choice surgical_strike
```
