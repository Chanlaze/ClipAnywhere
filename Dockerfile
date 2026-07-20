FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY clipanywhere ./clipanywhere

RUN adduser --disabled-password --gecos "" --home /app clipanywhere \
    && mkdir -p /data /config \
    && chown -R clipanywhere:clipanywhere /app /data /config

USER clipanywhere

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -m clipanywhere.healthcheck --config /config/server_config.json

CMD ["python", "-m", "clipanywhere.server", "--config", "/config/server_config.json"]

