# Deploy — Forked History / ANOR

Portable product image for **Dawes now**, **Ganymede / Nauvoo later**.  
Model and media endpoints are **env-only** (`LLM_URL`, `IMAGE_URL`, `TTS_URL`). No hosts are baked into the image.

## Quick start (Docker Compose)

```bash
# From repo root
cp .env.example .env   # edit URLs/keys on the host only — never commit .env

# Offline-safe boot (mock media). Prefer --env-file so keys never enter the image.
export ANOR_MOCK_MEDIA=1
docker compose --env-file .env up --build -d

# Site
open http://127.0.0.1:8787
# Health (slim public payload)
curl -s http://127.0.0.1:8787/api/health | python3 -m json.tool
```

## Point at the fleet (Dawes)

On the host, set real endpoints. From inside the container, the Docker host is
`host.docker.internal` (wired via `extra_hosts` in `docker-compose.yml`).

```bash
# Example — Ollama + Comfy + local TTS on the same machine as Docker
export ANOR_MOCK_MEDIA=0
export LLM_URL=http://host.docker.internal:11434/v1
export LLM_MODEL=qwen2.5:32b
export IMAGE_URL=http://host.docker.internal:8188
export IMAGE_BACKEND=comfy
export TTS_URL=http://host.docker.internal:8880/v1
docker compose up --build -d
```

Ganymede / Nauvoo: same compose file; only change the URL values (or `.env`).

## Guardrails

| Rule | How this deploy respects it |
|------|------------------------------|
| No secrets in image/repo | `.env` is gitignored; compose uses `${VAR}` substitution |
| Public packs only | Image copies `scenarios/public/` only |
| No auto-publish | No Postiz/TikTok/YouTube steps in compose |
| Speculation labels | Unchanged product code; packs keep `speculation_level` |
| Mock fallback | Default `ANOR_MOCK_MEDIA=1` until you flip it |

## Without Docker

```bash
export ANOR_MOCK_MEDIA=1
python3 -m webapp.server --host 0.0.0.0 --port 8787
```

## Volumes

Rendered videos persist in the named volume `anor_videos` → `/app/outputs/videos`.
