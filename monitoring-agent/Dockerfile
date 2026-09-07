FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    openssh-client \
    libpq-dev \
    gcc \
    g++ \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY requirements.lock .
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.lock && pip check

COPY . .

RUN useradd --uid 1000 --create-home app && mkdir -p /app/backups && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
