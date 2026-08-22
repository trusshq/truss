# Truss kernel — production image
FROM python:3.11-slim

WORKDIR /app

# deps first for layer caching (--no-install-project: the local package layout
# isn't installable; we run the source tree directly with `uv run`)
COPY pyproject.toml uv.lock* ./
RUN pip install --no-cache-dir uv \
    && (uv sync --frozen --no-dev --no-install-project 2>/dev/null || uv sync --no-dev --no-install-project)

COPY . .

# non-root runtime user
RUN useradd --create-home --uid 1000 truss \
    && mkdir -p /app/plugins \
    && chown -R truss:truss /app
USER truss

ENV TRUSS_EXTERNAL_PLUGINS_DIR=/app/plugins
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status==200 else 1)"

# run uvicorn from the synced venv directly (avoids `uv run` re-syncing the
# non-installable local package at container start)
CMD ["/app/.venv/bin/uvicorn", "truss_kernel.main:app", "--host", "0.0.0.0", "--port", "8000"]
