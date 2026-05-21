# -- build stage --
FROM python:3.11-slim AS builder

WORKDIR /build
COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir --prefix=/install .

# -- runtime stage --
FROM python:3.11-slim

LABEL org.opencontainers.image.title="frigate-protect-events"
LABEL org.opencontainers.image.description="Bridge Frigate AI detections into UniFi Protect as native smart detection events"
LABEL org.opencontainers.image.source="https://github.com/jasonmadigan/frigate-protect-events"
LABEL org.opencontainers.image.version="0.1.0"

RUN groupadd -r fpe && useradd -r -g fpe -d /app fpe

WORKDIR /app

COPY --from=builder /install/lib /usr/local/lib
COPY --from=builder /build/src /app/src

RUN mkdir -p /app/config /app/ssh && chown -R fpe:fpe /app

USER fpe

ENV FPE_CONFIG=/app/config/config.yaml

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD kill -0 1 || exit 1

ENTRYPOINT ["python", "-m", "frigate_protect_events"]
