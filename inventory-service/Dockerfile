# _______________________________ Build stage _______________________________

FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y     libjpeg-dev     zlib1g-dev     && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# _______________________________ Runtime stage _______________________________

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y     libjpeg62-turbo     zlib1g     curl     && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN adduser --disabled-password --gecos "" appuser

COPY . .

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8005

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3     CMD curl -f http://localhost:8005/api/inventory/stock-locations/ || exit 1

CMD ["gunicorn", "inventory_service.wsgi:application",      "--bind", "0.0.0.0:8005",      "--workers", "2",      "--timeout", "60"]
