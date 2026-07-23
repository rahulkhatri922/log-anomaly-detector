"""Business logic: ingest logs, train, detect, and expose metrics."""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from pipeline import features as feat
from pipeline import ml, parser
from pipeline.features import FEATURE_COLUMNS

from .database import MODEL_PATH, to_naive_utc
from .db_models import Anomaly, LogEntry


# --- model store --------------------------------------------------------

def model_exists() -> bool:
    return MODEL_PATH.exists()


def load_model() -> ml.ModelBundle | None:
    return ml.load_bundle(MODEL_PATH) if MODEL_PATH.exists() else None


def _window_seconds(bundle) -> int:
    return bundle.window_seconds if bundle else 60


# --- ingest -------------------------------------------------------------

def ingest_text(db: Session, text: str) -> dict:
    parsed = parser.parse_text(text)
    total_lines = sum(1 for ln in text.splitlines() if ln.strip())
    if not parsed:
        return {"stored": 0, "parsed": 0, "skipped": total_lines, "format": "unknown"}

    upload_id = uuid.uuid4().hex
    detected_format = parser.detect_format(text)
    rows = [
        LogEntry(
            timestamp=to_naive_utc(p.timestamp),
            level=p.level,
            source=p.source[:64],
            message=p.message,
            status_code=p.status_code,
            response_time_ms=p.response_time_ms,
            ip=p.ip,
            log_format=p.log_format,
            upload_id=upload_id,
        )
        for p in parsed
    ]
    db.bulk_save_objects(rows)
    db.commit()

    times = [to_naive_utc(p.timestamp) for p in parsed]
    return {
        "upload_id": upload_id,
        "stored": len(rows),
        "parsed": len(parsed),
        "skipped": total_lines - len(parsed),
        "format": detected_format,
        "time_range": {"start": min(times).isoformat(), "end": max(times).isoformat()},
    }


# --- queries ------------------------------------------------------------

def _logs_in_range(db: Session, start=None, end=None) -> list[LogEntry]:
    q = db.query(LogEntry)
    if start is not None:
        q = q.filter(LogEntry.timestamp >= to_naive_utc(start))
    if end is not None:
        q = q.filter(LogEntry.timestamp <= to_naive_utc(end))
    return q.order_by(LogEntry.timestamp).all()


def log_range(db: Session) -> dict | None:
    row = db.query(func.min(LogEntry.timestamp), func.max(LogEntry.timestamp)).one()
    if row[0] is None:
        return None
    return {"start": row[0].isoformat(), "end": row[1].isoformat()}


# --- train --------------------------------------------------------------

def train_model(db: Session, req) -> dict:
    logs = _logs_in_range(db, req.normal_start, req.normal_end)
    if not logs:
        raise ValueError("No logs in the selected normal range.")
    features = feat.build_features(logs, window_seconds=req.window_seconds)
    if len(features) < 2:
        raise ValueError(
            f"Only {len(features)} window(s) in range — need at least 2. "
            "Widen the range or lower window_seconds."
        )
    normal_range = {
        "start": req.normal_start.isoformat() if req.normal_start else None,
        "end": req.normal_end.isoformat() if req.normal_end else None,
    }
    bundle = ml.train(
        features,
        window_seconds=req.window_seconds,
        contamination=req.contamination,
        normal_range=normal_range,
    )
    ml.save_bundle(bundle, MODEL_PATH)
    return {"n_logs": len(logs), **bundle.summary()}


# --- detect -------------------------------------------------------------

def run_detection(db: Session, req) -> dict:
    bundle = load_model()
    if bundle is None:
        raise ValueError("No trained model. Call /train first.")

    logs = _logs_in_range(db, req.start, req.end)
    features = feat.build_features(logs, window_seconds=bundle.window_seconds)
    if features.empty:
        return {"flagged": 0, "total_windows": 0, "comparison": {"total_windows": 0}, "anomalies": []}

    detected = ml.detect(features, bundle, z_threshold=req.z_threshold)
    flagged = detected[detected["is_anomaly"]]

    existing = {a.window_start: a for a in db.query(Anomaly).all()}
    keep = set()
    for idx, row in flagged.iterrows():
        ws = to_naive_utc(idx.to_pydatetime())
        keep.add(ws)
        a = existing.get(ws) or Anomaly(window_start=ws, label=None)
        if a.id is None:
            db.add(a)
        a.window_end = ws + timedelta(seconds=bundle.window_seconds)
        a.iforest_score = float(row["iforest_score"])
        a.max_abs_z = float(row["max_abs_z"])
        a.agreement = row["agreement"]
        a.detectors = list(row["detectors"])
        a.triggered_metrics = list(row["triggered_metrics"])
        a.abnormal_features = list(row["abnormal_features"])
        a.metrics = {c: float(row[c]) for c in FEATURE_COLUMNS}
    # drop windows that are no longer anomalous
    for ws, a in existing.items():
        if ws not in keep:
            db.delete(a)
    db.commit()

    return {
        "flagged": int(len(flagged)),
        "total_windows": int(len(detected)),
        "comparison": ml.comparison_summary(detected),
        "z_threshold": req.z_threshold,
    }


# --- read models --------------------------------------------------------

def anomaly_to_dict(a: Anomaly) -> dict:
    return {
        "id": a.id,
        "window_start": a.window_start.isoformat(),
        "window_end": a.window_end.isoformat(),
        "iforest_score": round(a.iforest_score, 4),
        "max_abs_z": round(a.max_abs_z, 3),
        "agreement": a.agreement,
        "detectors": a.detectors,
        "triggered_metrics": a.triggered_metrics,
        "abnormal_features": a.abnormal_features,
        "metrics": a.metrics,
        "label": a.label,
    }


def list_anomalies(db: Session, label=None, detector=None) -> list[dict]:
    q = db.query(Anomaly).order_by(Anomaly.window_start)
    if label:
        q = q.filter(Anomaly.label == label)
    rows = q.all()
    if detector:
        rows = [a for a in rows if detector in (a.detectors or [])]
    return [anomaly_to_dict(a) for a in rows]


def label_anomaly(db: Session, anomaly_id: int, label: str) -> dict | None:
    a = db.get(Anomaly, anomaly_id)
    if a is None:
        return None
    a.label = label
    db.commit()
    return anomaly_to_dict(a)


def timeseries(db: Session, start=None, end=None) -> dict:
    bundle = load_model()
    logs = _logs_in_range(db, start, end)
    features = feat.build_features(logs, window_seconds=_window_seconds(bundle))
    anomaly_map = {a.window_start: a for a in db.query(Anomaly).all()}

    points = []
    for idx, row in features.iterrows():
        ws = to_naive_utc(idx.to_pydatetime())
        a = anomaly_map.get(ws)
        rec = {"window_start": idx.isoformat()}
        rec.update({c: (None if row[c] != row[c] else round(float(row[c]), 4)) for c in FEATURE_COLUMNS})
        rec["is_anomaly"] = a is not None
        rec["detectors"] = a.detectors if a else []
        rec["iforest_score"] = round(a.iforest_score, 4) if a else None
        points.append(rec)

    return {
        "window_seconds": _window_seconds(bundle),
        "features": FEATURE_COLUMNS,
        "points": points,
    }


def evaluation(db: Session) -> dict:
    anomalies = db.query(Anomaly).all()
    bundle = load_model()
    logs = _logs_in_range(db)
    total_windows = len(feat.build_features(logs, window_seconds=_window_seconds(bundle)))

    labeled = [a for a in anomalies if a.label]
    tp = sum(1 for a in labeled if a.label == "true_positive")
    fp = sum(1 for a in labeled if a.label == "false_positive")
    precision = round(tp / (tp + fp), 3) if (tp + fp) else None

    return {
        "total_windows": total_windows,
        "flagged_windows": len(anomalies),
        "anomaly_rate": round(len(anomalies) / total_windows, 4) if total_windows else 0.0,
        "labeled": len(labeled),
        "true_positives": tp,
        "false_positives": fp,
        "precision": precision,
        "note": (
            "Precision is computed from your labels on flagged windows. "
            "Recall/F1 require labeling normal (unflagged) windows too."
            if labeled
            else "Label flagged anomalies as true/false positive to compute precision."
        ),
    }


def status(db: Session) -> dict:
    bundle = load_model()
    return {
        "log_count": db.query(func.count(LogEntry.id)).scalar(),
        "anomaly_count": db.query(func.count(Anomaly.id)).scalar(),
        "log_range": log_range(db),
        "model_trained": bundle is not None,
        "model": bundle.summary() if bundle else None,
    }
