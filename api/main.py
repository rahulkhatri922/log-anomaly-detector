"""FastAPI application: upload logs, train, detect, and serve metrics."""
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import service
from .database import Base, engine, get_db
from .schemas import DetectRequest, LabelRequest, TrainRequest

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Log Anomaly Detector",
    description="Ingest logs, learn normal behavior, and flag anomalies with "
    "Isolation Forest + Z-score detectors.",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/status")
def status(db: Session = Depends(get_db)):
    return service.status(db)


@app.post("/api/logs/upload")
async def upload_logs(file: UploadFile = File(...), db: Session = Depends(get_db)):
    raw = await file.read()
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Could not decode file as UTF-8.")
    result = service.ingest_text(db, text)
    if result["stored"] == 0:
        raise HTTPException(
            status_code=422,
            detail="No log lines could be parsed. Supported: Apache/Nginx, JSON, syslog.",
        )
    return result


@app.post("/api/train")
def train(req: TrainRequest, db: Session = Depends(get_db)):
    try:
        return service.train_model(db, req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/detect")
def detect(req: DetectRequest, db: Session = Depends(get_db)):
    try:
        return service.run_detection(db, req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/anomalies")
def anomalies(
    label: str | None = Query(default=None),
    detector: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return {"anomalies": service.list_anomalies(db, label=label, detector=detector)}


@app.post("/api/anomalies/{anomaly_id}/label")
def label_anomaly(anomaly_id: int, req: LabelRequest, db: Session = Depends(get_db)):
    result = service.label_anomaly(db, anomaly_id, req.label)
    if result is None:
        raise HTTPException(status_code=404, detail="Anomaly not found.")
    return result


@app.get("/api/metrics/timeseries")
def timeseries(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    from datetime import datetime

    def _parse(v):
        return datetime.fromisoformat(v) if v else None

    try:
        return service.timeseries(db, _parse(start), _parse(end))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid date: {exc}")


@app.get("/api/evaluation")
def evaluation(db: Session = Depends(get_db)):
    return service.evaluation(db)
