# DRAFT — ELO-007 invasion branch — SENSITIVE — for approval

**Status:** DRAFT · do not publish without Ryan  
**Platforms:** YouTube only (not TikTok first cut)  
**Speculation:** SIMULATED high-commitment branch  
**Pack:** `scenarios/public/ELO-007.json`

## YouTube title
SPECULATION: Full invasion of Cuba in October 1962

## YouTube description
⚠️ SIMULATED counterfactual. The historical opening move is the naval quarantine.

We do not glamorize invasion. We do not invent “clean regime-change” montage endings. The only responsible claim: a ground war against an island with Soviet forces present is the largest conventional bet of the three EXCOMM branches — and the path most likely to produce direct U.S.–Soviet combat under nuclear fog.

🧪 Simulated · 📗 baseline = quarantine first  
No scoreboard. No triumphal thumbnail of flags on Havana.

If you want the historical episode, watch the quarantine companion. For a related near-miss the same month, see ELO-013 (B-59).

## Why gated
High harm potential if clipped out of context. Requires explicit on-screen 🧪 labels and a pinned comment stating the historical outcome (quarantine, not invasion).

## Render (offline-safe)
```bash
export ANOR_MOCK_MEDIA=1
python3 -m pipeline.cli video --scenario ELO-007 --choice invasion
```
