FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    ROCKYROAD_API_HOST=0.0.0.0 \
    ROCKYROAD_API_PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 rockyroad

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /usr/local/bin/uv
COPY pyproject.toml README.md /app/
COPY config /app/config
COPY services/api /app/services/api
COPY infra/api/entrypoint.sh /usr/local/bin/rockyroad-api-entrypoint

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/services/api/src" \
    ROCKYROAD_EXTENSIONS_DIR="/opt/duckdb/extensions"

RUN uv sync --no-dev \
    && mkdir -p /opt/duckdb/extensions /state \
    && python -c "import duckdb; c=duckdb.connect(); c.execute(\"SET extension_directory='/opt/duckdb/extensions'\"); c.execute('INSTALL spatial'); c.execute('INSTALL fts')" \
    && chmod 755 /usr/local/bin/rockyroad-api-entrypoint \
    && chown -R rockyroad:rockyroad /opt/duckdb /state

USER rockyroad
EXPOSE 8000

ENTRYPOINT ["rockyroad-api-entrypoint"]
CMD ["uvicorn", "rockyroad_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
