# DRAFT — ELO-008 delay longer (counterfactual) — for approval

**Status:** DRAFT · do not publish  
**Platforms:** YouTube, TikTok (only with hard 🧪 labels)  
**Speculation:** SIMULATED branch — must stay labeled on-screen  
**Pack:** `scenarios/public/ELO-008.json`

## YouTube title
SPECULATION: What if Overlord waited longer for perfect weather?

## YouTube description
⚠️ This video’s middle act is labeled SIMULATION — not history.

Documented fact: after a short hold, Eisenhower **goes** for 6 June.
Famous counterfactual: wait longer for cleaner seas and sky.

We hold the baseline honest, then fork. No guaranteed easier landing. No automatic catastrophe. The honest claim is the trade between weather quality and secrecy, fatigue, and calendar. Label: 🧪 simulated.

**Provenance:** 📗 6 June go is documented · 🧪 longer delay is simulated  
Sources: public Overlord operational histories and weather-decision literature.

If you want the historical episode, watch the companion go draft.

#althistory #dday #ww2 #speculationlabeled

## TikTok caption
What if they wait longer for perfect weather?
We label this 🧪 SIMULATED. History took the narrow window.
Patience can save boats — or burn surprise.
#althistory #historytok #ww2

## Mandatory on-screen labels
- Cold open: 📗 DOCUMENTED (go for 6 June)
- Fork title card: 🧪 SIMULATED COUNTERFACTUAL
- End card: “Baseline unchanged: they went.”

## Render (offline-safe)
```bash
export ANOR_MOCK_MEDIA=1
python3 -m pipeline.cli video --scenario ELO-008 --choice delay_longer
```
