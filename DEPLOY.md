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

## Security runtime

The image runs as **non-root** user `anor` (**uid/gid 10001**). Compose sets
`user: "10001:10001"` so it matches the image. Do not override with `user: root`
unless you are debugging.

## Guardrails

| Rule | How this deploy respects it |
|------|------------------------------|
| No secrets in image/repo | `.env` is gitignored; compose uses `${VAR}` substitution |
| Public packs only | Image copies `scenarios/public/` only |
| No auto-publish | No Postiz/TikTok/YouTube steps in compose |
| Speculation labels | Unchanged product code; packs keep `speculation_level` |
| Mock fallback | Default `ANOR_MOCK_MEDIA=1` until you flip it |
| Non-root process | `USER anor` (10001) in Dockerfile + compose `user` |

## Without Docker

```bash
export ANOR_MOCK_MEDIA=1
python3 -m webapp.server --host 0.0.0.0 --port 8787
```

## Volumes

Rendered videos persist in the named volume `anor_videos` → `/app/outputs/videos`.

If the volume was created by an older root-owned container and the app cannot
write MP4s, fix ownership once (host with Docker):

```bash
docker run --rm -v anor_anor_videos:/v alpine chown -R 10001:10001 /v
# volume name may differ — check: docker volume ls | grep anor
```
