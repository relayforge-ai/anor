# DRAFT — ELO-005 localization gamble (dramatized) — for approval

**Status:** DRAFT · do not publish  
**Platforms:** YouTube, TikTok (with dramatized / 🧪 labels)  
**Speculation:** DRAMATIZED process — not a documented alternate war plan  
**Pack:** `scenarios/public/ELO-005.json`

## YouTube title
DRAMATIZED: What if July 1914 stayed a “local” Balkan war?

## YouTube description
⚠️ Dramatized process — not a second history book.

Documented baseline: blank cheque and the cascade into general war.
This cut studies the localization gamble: frame Austria’s action as Serbia-only and bet Russia will not fully come in.

Hope is not a plan. We label the emphasis so clips cannot pretend this is “what really happened instead.”

📗 Baseline = blank cheque · 🧪 this cut = dramatized localization bet  
Companions: historical blank cheque; restrain simulation.

#althistory #ww1 #julycrisis #1914

## TikTok caption
What if they bet the war stays Balkan?
Dramatized process. Not secret history.
📗 The cascade was general in the real timeline.
#historytok #ww1 #1914

## Mandatory on-screen labels
- Cold open: 📗 DOCUMENTED baseline
- Fork card: 🧪 DRAMATIZED EMPHASIS
- End: “Not a claim of a clean localized war.”

## Render (offline-safe)
```bash
export ANOR_MOCK_MEDIA=1
python3 -m pipeline.cli video --scenario ELO-005 --choice localize_only
```
