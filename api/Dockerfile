# Build context is the repository root (see docker-compose.yml) so the image can
# include the pipeline package, the API, and the scripts together.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pipeline/ ./pipeline/
COPY api/ ./api/
COPY scripts/ ./scripts/
COPY sample_data/ ./sample_data/

RUN chmod +x api/entrypoint.sh
EXPOSE 8000
CMD ["./api/entrypoint.sh"]
