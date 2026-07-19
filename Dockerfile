# Forked History / ANOR — portable product image
# Endpoints (LLM_URL, IMAGE_URL, TTS_URL) come from env at runtime — never baked in.
# Default ANOR_MOCK_MEDIA=1 so the site boots offline; flip to 0 when fleet URLs are set.

FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Application source only (see .dockerignore). No .env / secrets.
COPY LICENSE README.md PIPELINE.md ./
COPY pipeline/ ./pipeline/
COPY webapp/ ./webapp/
COPY scenarios/public/ ./scenarios/public/
COPY scenarios/schema/ ./scenarios/schema/
COPY scripts/ ./scripts/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ANOR_MOCK_MEDIA=1 \
    HOST=0.0.0.0 \
    PORT=8787

EXPOSE 8787

# Stdlib health probe — no curl dependency
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=3)"

# Bind all interfaces inside the container so compose port maps work.
CMD ["python", "-m", "webapp.server", "--host", "0.0.0.0", "--port", "8787"]
