# DRAFT — ELO-008 Overlord go (historical) — for approval

**Status:** DRAFT · do not publish  
**Platforms:** YouTube (long + Short), TikTok  
**Speculation:** none on the spine — historical go for 6 June  
**Pack:** `scenarios/public/ELO-008.json` (public ELOSTIRION only)

## YouTube title
June 1944: Eisenhower gives the go for D-Day

## YouTube description
Thousands of ships and aircraft are wound tight. Forecasts disagree in the details and agree on the danger. A wrong call wastes surprise, lives, and months of preparation.

Documented path: after a brief weather delay, the Supreme Commander orders the invasion for 6 June 1944. The lodgement is costly and contested — and it holds.

This is not a triumph montage. It is a command bet under incomplete weather certainty.

📗 Documented baseline · public Overlord / D-Day decision historiography  
Series: ANOR Fork / ELOSTIRION — real decision points; speculation labeled when we fork.

#dday #overlord #ww2 #1944 #history

## TikTok caption
June 1944. Armada ready. Weather marginal.
Go now — or wait?
📗 Documented: the go for the sixth.
#history #ww2 #dday #fyp

## On-screen beats
1. Maps · tide tables · weather charts
2. The fork: go / delay / postpone
3. Historical choice: go for 6 June
4. Beaches under fire · lodgement holds
5. 📗 Documented baseline

## Render (offline-safe)
```bash
export ANOR_MOCK_MEDIA=1   # or set LLM_URL IMAGE_URL TTS_URL on Dawes
python3 -m pipeline.cli video --scenario ELO-008 --choice historical
```
