# syntax=docker/dockerfile:1
# Multi-stage build for the customer-retention-workflow plugin.

FROM python:3.11-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# --- dependency layer (cached) ---
COPY pyproject.toml README.md ./
RUN pip install --upgrade pip && pip install ".[dev]"

# --- application layer ---
COPY src ./src
COPY scripts ./scripts
COPY app ./app
COPY skills ./skills
COPY manifest.json .codex-plugin ./
COPY tests ./tests

# Run as a non-root user (security best practice).
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

# Streamlit UI port (used by the `ui` compose service).
EXPOSE 8501

# Default: run the workflow over the bundled sample dataset.
ENTRYPOINT ["python", "scripts/run_workflow.py"]
CMD ["--quiet"]
