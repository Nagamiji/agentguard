# Production image for the control plane (and worker — same image, different command).
# Multi-stage: build deps stay out of the runtime layer.
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Dependency layer: keyed on pyproject alone so source edits don't reinstall the world.
COPY pyproject.toml README.md ./
COPY src ./src
# Use a regular (non-editable) install so the package is fully contained in the venv
# and does not need /build/src to exist in the runtime stage.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install -U pip setuptools wheel \
    && /opt/venv/bin/pip install --no-build-isolation .


FROM python:3.12-slim AS runtime

# psycopg[binary] ships its own libpq, so no system postgres client is needed.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Non-root: the app never needs write access to its own code.
RUN useradd --create-home --uid 10001 keel

COPY --from=builder /opt/venv /opt/venv
COPY migrations /app/migrations
COPY alembic.ini /app/alembic.ini

WORKDIR /app
USER keel

EXPOSE 8000

# No secrets baked in — config arrives via KEEL_* env vars at runtime (src/keel/config.py).
CMD ["uvicorn", "keel.main:app", "--host", "0.0.0.0", "--port", "8000"]
