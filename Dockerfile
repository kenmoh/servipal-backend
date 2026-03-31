# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim as builder

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Enable bytecode compilation for faster startup
ENV UV_COMPILE_BYTECODE=1

# Copy only dependency files (leverage docker layer caching)
COPY pyproject.toml uv.lock ./

# Install production dependencies only
# --no-dev: Excludes dev dependencies
# --frozen: Uses exactly what's in uv.lock
# --no-install-project: Project code copied later
RUN uv sync --frozen --no-dev --no-install-project

# ============================================================
# Production stage - minimal final image
# ============================================================
FROM python:${PYTHON_VERSION}-slim

WORKDIR /app

# Copy pre-built virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Enable virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Copy only application code (everything else excluded via .dockerignore)
# .dockerignore excludes: tests/, docs/, postman/, .env, .git, etc.
COPY app/ app/

# Copy minimal config files
COPY pyproject.toml uv.lock ./

# Create non-root user for security
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/nonexistent" \
    --shell "/sbin/nologin" \
    --no-create-home \
    --uid "${UID}" \
    appuser

USER appuser

# Set environment variables
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

# Run the application
# We use the shell form or strict exec form. 
# Cloud Run injects the PORT env var.
CMD fastapi run --port $PORT
