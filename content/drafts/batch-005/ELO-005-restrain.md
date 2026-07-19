# DRAFT — ELO-005 restrain Vienna (counterfactual) — for approval

**Status:** DRAFT · do not publish  
**Platforms:** YouTube, TikTok (only with hard 🧪 labels)  
**Speculation:** SIMULATED branch — must stay labeled on-screen  
**Pack:** `scenarios/public/ELO-005.json`

## YouTube title
SPECULATION: What if Berlin restrained Vienna in July 1914?

## YouTube description
⚠️ This video’s middle act is labeled SIMULATION — not history.

Documented fact: Germany issues strong support for a hard Austrian course (blank cheque).
Famous counterfactual: condition support on diplomacy first; refuse a free hand.

We hold the baseline honest, then fork. No tidy “no Great War” ending. Restraining the ally changes tempo and risk — it does not erase nationalism or other flashpoints. Label: 🧪 simulated.

**Provenance:** 📗 blank cheque is documented · 🧪 restrain path is simulated  
Sources: public diplomatic histories of the July Crisis.

If you want the historical episode, watch the companion blank-cheque draft.

#althistory #ww1 #julycrisis #speculationlabeled

## TikTok caption
What if Berlin says not yet — diplomacy first?
We label this 🧪 SIMULATED. History records the blank cheque.
Tempo ≠ guaranteed peace.
#althistory #historytok #ww1

## Mandatory on-screen labels
- Cold open: 📗 DOCUMENTED (blank cheque; cascade followed)
- Fork title card: 🧪 SIMULATED COUNTERFACTUAL
- End card: “Baseline unchanged: support was issued.”

## Render (offline-safe)
```bash
export ANOR_MOCK_MEDIA=1
python3 -m pipeline.cli video --scenario ELO-005 --choice restrain
```
