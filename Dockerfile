# Stage 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /app

# Instala uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copia archivos de dependencias primero (aprovecha cache de Docker)
COPY pyproject.toml uv.lock ./

# Instala dependencias en un virtualenv aislado
RUN uv sync --frozen --no-dev --no-install-project

# Stage 2: Runtime
FROM python:3.12-slim AS runtime

WORKDIR /app

# libpq necesaria para psycopg2-binary en runtime
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*

# Usuario no-root por seguridad
RUN adduser --disabled-password --gecos "" appuser

# Copia el virtualenv desde el builder
COPY --from=builder /app/.venv /app/.venv

# Copia el codigo fuente
COPY factor_bridge_agent/ ./factor_bridge_agent/
COPY api/ ./api/

# Activa el virtualenv
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

EXPOSE 8080

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
