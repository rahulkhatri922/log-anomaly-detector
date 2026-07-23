"""Rolling time-window feature engineering.

Buckets parsed logs into fixed windows (default 60s) and computes the signals an
anomaly detector cares about: volume, error rate, latency, client spread, the
5xx/2xx ratio, and the Shannon entropy of message templates (which spikes when
a burst of never-before-seen messages appears).
"""
from __future__ import annotations

import math
import re
from collections import Counter

import pandas as pd

FEATURE_COLUMNS = [
    "request_count",
    "error_rate",
    "avg_response_time_ms",
    "unique_ips",
    "ratio_5xx_2xx",
    "message_entropy",
]

_NUM_RE = re.compile(r"\d+")
_HEX_RE = re.compile(r"0x[0-9a-fA-F]+")


def templatize(message: str) -> str:
    """Collapse a message to a template so varying ids/numbers group together."""
    t = _HEX_RE.sub("#", message or "")
    t = _NUM_RE.sub("#", t)
    return " ".join(t.split()).lower()


def _entropy(values) -> float:
    counts = Counter(values)
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def logs_to_frame(logs) -> pd.DataFrame:
    """Turn a list of ParsedLog into a tidy DataFrame (one row per log)."""
    rows = []
    for log in logs:
        rows.append(
            {
                "timestamp": pd.to_datetime(log.timestamp, utc=True),
                "level": log.level,
                "source": log.source,
                "status_code": log.status_code,
                "response_time_ms": log.response_time_ms,
                "ip": log.ip,
                "template": templatize(log.message),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def _window_features(group: pd.DataFrame) -> dict:
    n = len(group)
    status = group["status_code"].dropna()
    n_5xx = int(((status >= 500) & (status < 600)).sum())
    n_2xx = int(((status >= 200) & (status < 300)).sum())
    n_error = int((group["level"] == "ERROR").sum() + (group["level"] == "CRITICAL").sum())
    rt = group["response_time_ms"].dropna()
    return {
        "request_count": n,
        "error_rate": round(n_error / n, 4) if n else 0.0,
        "avg_response_time_ms": round(float(rt.mean()), 2) if len(rt) else 0.0,
        "unique_ips": int(group["ip"].dropna().nunique()),
        "ratio_5xx_2xx": round(n_5xx / max(1, n_2xx), 4),
        "message_entropy": round(_entropy(group["template"]), 4),
    }


def build_features(logs, window_seconds: int = 60) -> pd.DataFrame:
    """Aggregate logs into per-window feature rows indexed by window start."""
    df = logs_to_frame(logs)
    if df.empty:
        empty = pd.DataFrame(columns=FEATURE_COLUMNS)
        empty.index.name = "window_start"
        return empty

    freq = f"{window_seconds}s"
    df = df.set_index("timestamp")
    grouped = df.groupby(pd.Grouper(freq=freq))

    records = {}
    for window_start, group in grouped:
        if len(group) == 0:
            continue
        records[window_start] = _window_features(group)

    features = pd.DataFrame.from_dict(records, orient="index")
    features.index.name = "window_start"
    features = features.sort_index()
    return features[FEATURE_COLUMNS]


def features_to_records(features: pd.DataFrame) -> list[dict]:
    """Serialize a feature frame to JSON-friendly records (for the API/UI)."""
    out = []
    for idx, row in features.iterrows():
        rec = {"window_start": idx.isoformat()}
        rec.update({col: (None if pd.isna(row[col]) else row[col]) for col in FEATURE_COLUMNS})
        out.append(rec)
    return out
