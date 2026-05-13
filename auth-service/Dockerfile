# _______________________________ Build stage _______________________________

FROM python:3.11-slim AS builder

WORKDIR /app


# install build dependencies for Pillow
RUN apt-get update && apt-get install -y \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# create virtual environment to isolate the packages from the system python
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# copy only the requirements file to leverage Docker cache
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# _______________________________ Runtime stage _______________________________


FROM python:3.11-slim

WORKDIR /app

# Runtime system libs only (no build tools)
RUN apt-get update && apt-get install -y \
    libjpeg62-turbo \
    zlib1g \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only the venv from builder — not the build tools
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user to run the application
RUN adduser --disabled-password --gecos "" appuser

# Copy source code
COPY . .

# Give appuser ownership of the application files
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8001

# Health check — Docker marks container unhealthy if this fails
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/api/users/ || exit 1

CMD ["gunicorn", "auth_service.wsgi:application", \
     "--bind", "0.0.0.0:8001", \
     "--workers", "2", \
     "--timeout", "60"]
