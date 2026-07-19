# DRAFT — ELO-006 force corridors (counterfactual) — for approval

**Status:** DRAFT · do not publish  
**Platforms:** YouTube, TikTok (only with hard 🧪 labels)  
**Speculation:** SIMULATED branch — must stay labeled on-screen  
**Pack:** `scenarios/public/ELO-006.json`

## YouTube title
SPECULATION: What if the West forced the Berlin land corridors in 1948?

## YouTube description
⚠️ This video’s middle act is labeled SIMULATION — not history.

Documented fact: the Western Allies mount a sustained **airlift**.
Famous counterfactual: reopen road and rail under arms.

We hold the baseline honest, then fork. No tidy armored victory montage. No guaranteed general war. The honest claim is escalation risk versus logistics patience. Label: 🧪 simulated.

**Provenance:** 📗 airlift is documented · 🧪 force path is simulated  
Sources: public histories of the Berlin Blockade and Airlift.

If you want the historical episode, watch the companion airlift draft.

#althistory #coldwar #berlin #speculationlabeled

## TikTok caption
What if the answer is force the roads?
We label this 🧪 SIMULATED. History chose the airlift.
Faster story. Thinner fuse.
#althistory #historytok #coldwar

## Mandatory on-screen labels
- Cold open: 📗 DOCUMENTED (airlift; blockade ends 1949)
- Fork title card: 🧪 SIMULATED COUNTERFACTUAL
- End card: “Baseline unchanged: they flew.”

## Render (offline-safe)
```bash
export ANOR_MOCK_MEDIA=1
python3 -m pipeline.cli video --scenario ELO-006 --choice force_corridors
```
