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
COPY app/ app/

# Install production dependencies only
# --no-dev: Excludes dev dependencies
# --frozen: Uses exactly what's in uv.lock
# --link-mode=copy: Ensures dependencies are copied, not symlinked, since we copy the .venv across stages
RUN uv sync --frozen --no-dev --link-mode=copy

# ============================================================
# Production stage - minimal final image
# ============================================================
FROM python:${PYTHON_VERSION}-slim

WORKDIR /app

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

# Copy pre-built virtual environment from builder
COPY --chown=appuser:appuser --from=builder /app/.venv /app/.venv

# Enable virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Copy only application code (everything else excluded via .dockerignore)
# .dockerignore excludes: tests/, docs/, postman/, .env, .git, etc.
COPY --chown=appuser:appuser app/ app/

# Copy minimal config files
COPY --chown=appuser:appuser pyproject.toml uv.lock ./

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

USER appuser

# Set environment variables
ENV PORT=8080
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8080

# Run the application
# CMD fastapi run --port $PORT
# CMD /app/.venv/bin/fastapi run --port $PORT
CMD ["/usr/local/bin/uv", "run", "fastapi", "run", "--host", "0.0.0.0", "--port", $PORT]
