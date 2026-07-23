"""Populate the app with demo data on first boot.

Loads the committed synthetic logs (or generates them), trains on the calm
opening stretch (before any injected anomaly), then runs detection — so a fresh
`docker compose up` lands on a dashboard that already tells a story. Idempotent:
does nothing if logs are already present.
"""
from datetime import datetime
from pathlib import Path

from api import service
from api.database import Base, SessionLocal, engine
from api.schemas import DetectRequest, TrainRequest

SAMPLE = Path("sample_data/app_logs.jsonl")


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if service.status(db)["log_count"] > 0:
            print("bootstrap: logs already present, skipping.")
            return

        if SAMPLE.exists():
            text = SAMPLE.read_text()
        else:
            from scripts.generate_logs import generate, to_json_line

            records, _ = generate(minutes=180, rate=60, seed=42)
            text = "\n".join(to_json_line(r) for r in records)

        ingest = service.ingest_text(db, text)
        print(f"bootstrap: ingested {ingest['stored']} logs ({ingest['format']}).")

        rng = service.log_range(db)
        start = datetime.fromisoformat(rng["start"])
        end = datetime.fromisoformat(rng["end"])
        # train on the first 35% of the timeline (before the first planted anomaly)
        normal_end = start + (end - start) * 0.35

        service.train_model(
            db, TrainRequest(normal_start=start, normal_end=normal_end, contamination=0.03)
        )
        result = service.run_detection(db, DetectRequest())
        print(f"bootstrap: trained + flagged {result['flagged']} anomaly windows.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
