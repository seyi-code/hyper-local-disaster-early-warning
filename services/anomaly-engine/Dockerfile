FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
RUN mkdir -p /app/config && chown -R appuser:appuser /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV CELLS_CONFIG_PATH=/app/config/cells.json

USER appuser

CMD ["python", "src/main.py"]
