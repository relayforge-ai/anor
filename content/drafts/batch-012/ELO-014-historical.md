# DRAFT — ELO-014 Gettysburg charge (historical) — for approval

**Status:** DRAFT · do not publish  
**Platforms:** YouTube (long + Short), TikTok  
**Speculation:** none on the spine — historical center assault  
**Pack:** `scenarios/public/ELO-014.json` (public ELOSTIRION only)

## YouTube title
3 July 1863: The charge on Cemetery Ridge

## YouTube description
July heat. Smoke over a stone wall. Two days already spent without a decision.

📗 Documented baseline: Lee orders a massed assault on the Union center. The attack fails under artillery and rifle fire. The Army of Northern Virginia later withdraws; initiative in the East shifts.

This is not a glory montage. It is a study in culmination, artillery preparation, and the cost of frontal assault against a coherent line.

Series: ANOR Fork / ELOSTIRION

#history #gettysburg #1863 #civilwar #decisionpoint

## TikTok caption
1863. Ridge holds. The order is charge.
📗 Documented center assault — and the break.
#historytok #gettysburg #civilwar

## On-screen beats
1. 3 July · heat and smoke
2. Ridge still holds
3. 📗 Order the charge
4. Assault fails
5. Campaign decision written

## Render (offline-safe)
```bash
export ANOR_MOCK_MEDIA=1
python3 -m pipeline.cli video --scenario ELO-014 --choice historical
```
