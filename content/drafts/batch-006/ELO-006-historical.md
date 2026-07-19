# DRAFT — ELO-006 Berlin Airlift (historical) — for approval

**Status:** DRAFT · do not publish  
**Platforms:** YouTube (long + Short), TikTok  
**Speculation:** none on the spine — historical airlift  
**Pack:** `scenarios/public/ELO-006.json` (public ELOSTIRION only)

## YouTube title
1948: Berlin is cut off — the West chooses the airlift

## YouTube description
Roads and rails into West Berlin go dark. Two million people need coal and bread. The map is small; the risk is not.

Documented path: supply the city by air rather than force the land corridors with armor. The airlift becomes a months-long logistics campaign. The blockade ends in 1949; the division of Germany hardens.

This is not a nostalgia montage. It is a study in firmness without a forced ground clash.

📗 Documented baseline · public Berlin Blockade / Airlift historiography  
Series: ANOR Fork / ELOSTIRION — real decision points; speculation labeled when we fork.

#berlinairlift #coldwar #1948 #history #berlin

## TikTok caption
1948. Berlin cut off.
Fly the supplies — or force the roads?
📗 Documented: the airlift. The city holds.
#history #coldwar #berlin #fyp

## On-screen beats
1. Corridors closed · occupation map
2. The fork: airlift vs force
3. Historical choice: fly coal and flour
4. Months of schedules · weather · risk
5. 📗 Documented baseline

## Render (offline-safe)
```bash
export ANOR_MOCK_MEDIA=1   # or set LLM_URL IMAGE_URL TTS_URL on Dawes
python3 -m pipeline.cli video --scenario ELO-006 --choice historical
```
