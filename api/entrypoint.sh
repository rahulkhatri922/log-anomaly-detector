#!/usr/bin/env sh
set -e

python -c "from api.database import Base, engine; Base.metadata.create_all(bind=engine)"
python -m scripts.bootstrap || echo "bootstrap skipped"

echo "Starting API on :8000..."
exec uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2
