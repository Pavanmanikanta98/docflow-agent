# Backend image — used for the API, the ARQ worker, or both in one container.
#
# Build from the repo root:
#   docker build -f backend/Dockerfile -t docflow-backend .
# Run:
#   docker run --env-file .env -p 8000:8000 docflow-backend            # API
#   docker run --env-file .env docflow-backend bash backend/start.sh worker
#   docker run --env-file .env -p 8000:8000 docflow-backend bash backend/start.sh all

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Tesseract is a system binary; pytesseract only wraps it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# Dependencies first so code changes don't invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY alembic ./alembic
COPY backend ./backend
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 1000 appuser && chown -R appuser /app
USER appuser

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

CMD ["bash", "backend/start.sh", "api"]
