import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

# Point the app at a throwaway data dir BEFORE importing it.
_TMP = tempfile.mkdtemp(prefix="lad-test-")
os.environ["DATA_DIR"] = _TMP
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.database import MODEL_PATH, Base, engine  # noqa: E402
from api.main import app  # noqa: E402


@pytest.fixture
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    if MODEL_PATH.exists():
        MODEL_PATH.unlink()
    return TestClient(app)


def make_json_logs(minutes=30, rate=40, anomaly_minutes=(20, 21, 22), seed=7):
    """A normal baseline of JSON logs with an injected error/latency burst."""
    import random

    rng = random.Random(seed)
    start = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    lines = []
    for minute in range(minutes):
        base = start + timedelta(minutes=minute)
        anomalous = minute in anomaly_minutes
        count = rate * (5 if anomalous else 1)
        for _ in range(count):
            ts = base + timedelta(seconds=rng.uniform(0, 60))
            if anomalous and rng.random() < 0.6:
                status, rt, msg = rng.choice([500, 502, 503]), rng.uniform(800, 1500), "Database timeout"
            else:
                status, rt, msg = 200, rng.uniform(40, 120), "GET /api/x"
            lines.append(
                json.dumps(
                    {
                        "timestamp": ts.isoformat(),
                        "level": "ERROR" if status >= 500 else "INFO",
                        "source": "web",
                        "message": msg,
                        "status": status,
                        "response_time_ms": round(rt, 1),
                        "ip": f"10.0.0.{rng.randint(1, 50)}",
                    }
                )
            )
    return "\n".join(lines) + "\n"


@pytest.fixture
def sample_logs():
    return make_json_logs()
