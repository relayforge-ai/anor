# DRAFT — ELO-009 Dunkirk halt (historical) — for approval

**Status:** DRAFT · do not publish  
**Platforms:** YouTube (long + Short), TikTok  
**Speculation:** none on the spine — historical armor halt  
**Pack:** `scenarios/public/ELO-009.json` (public ELOSTIRION only)

## YouTube title
May 1940: German armor halts — and a fleet comes for Dunkirk

## YouTube description
The pocket is real. The sea is behind the Allies. German panzers could try to finish the job — or stop.

Documented path: armored thrusts pause short of an immediate coup de grâce. Weather, logistics, perimeter fighting, and a navy that will not quit combine into Operation Dynamo. Hundreds of thousands leave. Equipment is lost. Cadres return.

This is not a “miracle” meme. It is a study in operational tempo: every hour of halt is an hour ships can work.

📗 Documented baseline · established 1940 Flanders / Dynamo historiography  
Series: ANOR Fork / ELOSTIRION — real decision points; speculation labeled when we fork.

#dunkirk #ww2 #history #1940 #dynamo

## TikTok caption
May 1940. Pocket at the sea.
Armor could finish it — or halt.
📗 Documented: they halt. Ships come.
#history #ww2 #dunkirk #fyp

## On-screen beats
1. Channel map · pocket forming
2. The fork: press armor vs halt
3. Historical choice: halt / consolidate
4. Ships · moles · night lifts
5. 📗 Documented baseline

## Render (offline-safe)
```bash
export ANOR_MOCK_MEDIA=1   # or set LLM_URL IMAGE_URL TTS_URL on Dawes
python3 -m pipeline.cli video --scenario ELO-009 --choice historical
```
