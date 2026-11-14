# One container for any Docker host (Render, Cloud Run, a VPS, Hugging Face PRO):
# the Python API serves the API and the static Next.js site on $PORT.

# 1. Build the website.
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# 2. Python app.
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b poppler-utils ffmpeg \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /bin/uv

# Spaces run as user 1000.
RUN useradd -m -u 1000 user
USER user
WORKDIR /home/user/app
# KAHAANI_CACHE=0: a public server must never keep children's stories on disk.
ENV PATH=/home/user/app/.venv/bin:$PATH \
    UV_COMPILE_BYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=7860 \
    KAHAANI_CACHE=0

COPY --chown=user pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY --chown=user kahaani kahaani
COPY --chown=user samples samples
COPY --chown=user eval/briefs.jsonl eval/briefs.jsonl
COPY --from=web --chown=user /web/out web/out

EXPOSE 7860
CMD ["python", "-m", "kahaani.api"]
