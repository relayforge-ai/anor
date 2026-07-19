# Forked History — product site

Premium freemium surface for public ANOR / ELOSTIRION decision packs and explainers.

## Run

```bash
cd /path/to/anor

# ensure at least mock videos exist (optional)
export ANOR_MOCK_MEDIA=1
python3 -m pipeline.cli video --scenario ELO-003 --choice historical

# start the site
python3 -m webapp.server --host 127.0.0.1 --port 8787
# open http://127.0.0.1:8787
```

Also:

```bash
python3 -m pipeline.cli site --port 8787   # launches this product site
```

## Freemium model

| Surface | Free (Explorer) | Paid (Scholar · **$4.99/mo** recommended) |
|---------|-----------------|-------------------------------------------|
| Video | **1 full episode** of the viewer's choice | Entire library uncut |
| After free full | **25% preview** of each additional episode | Full |
| Studio | Authored forks, **labeled branch compare**, copy narrative | LLM re-render, custom seeds, export |
| Daily | 3 free fork counters (authored still works after) | Unlimited |

### Pricing suggestions (shown in UI)

1. **Explorer — $0** — museum sample: 1 full + 25% previews + basic forks + free compare  
2. **Scholar — $4.99/mo or $39/yr** *(recommended)* — full library + full studio  
3. **Council Seat — $12/mo or $99/yr** — priority re-sim / founding credit  
4. **Library Pass — $7.99 once / 90 days** — binge without subscription  

Rationale: coffee-scale, not Netflix. Funds sovereign GPU hours (Dawes → Nauvoo). Stripe is **stubbed** — Demo unlock for Ryan review.

## Architecture

```
webapp/
  server.py           # stdlib HTTP: SPA + API + video range requests
  data/catalog.json   # brand, pricing, video inventory
  static/             # HTML/CSS/JS (no build step)
```

Membership state is **localStorage** for this build (`fh:entitlements`). Swap for server sessions + Stripe webhooks before public money.

## Guardrails

- Public packs only (`scenarios/public/`)
- No MANDOS master sources
- Speculation labeled in studio + player
- No auto-publish to socials from this surface
