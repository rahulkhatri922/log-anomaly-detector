#!/usr/bin/env python
"""Generate realistic synthetic application logs with injected anomalies.

Produces a mostly-normal traffic timeline (diurnal-ish request rate, low error
rate, log-normal latencies) with three planted anomalies:

    * a traffic spike   (request volume jumps ~8x)
    * an error burst     (5xx rate jumps, new error templates appear)
    * a latency spike    (response times jump ~6x)

    python scripts/generate_logs.py                      # -> sample_data/app_logs.jsonl
    python scripts/generate_logs.py --format nginx       # nginx access-log format
    python scripts/generate_logs.py --minutes 240 --rate 80

A companion ``*_truth.json`` lists the anomalous minute-windows for reference.
"""
import argparse
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

NORMAL_ROUTES = [
    ("GET", "/api/products"),
    ("GET", "/api/orders"),
    ("GET", "/api/users/profile"),
    ("POST", "/api/cart/add"),
    ("POST", "/api/auth/login"),
    ("GET", "/health"),
    ("GET", "/api/search"),
]
ERROR_MESSAGES = [
    "Database connection timeout after 30s",
    "Upstream 502 from payment-service",
    "Unhandled exception: NullPointerException in OrderController",
    "Redis connection refused",
    "OOMKilled: worker exceeded memory limit",
]


def _diurnal(minute: int, total: int) -> float:
    # a mild, slow drift so "normal" is fairly stationary (anomalies should be
    # what stands out, not ordinary daily variation)
    return 1.0 + 0.12 * math.sin(2 * math.pi * minute / max(1, total))


def _windows(total: int) -> dict:
    return {
        "traffic_spike": range(int(total * 0.38), int(total * 0.42)),
        "error_burst": range(int(total * 0.60), int(total * 0.64)),
        "latency_spike": range(int(total * 0.80), int(total * 0.84)),
    }


def _status_and_latency(rng, in_error, in_latency):
    r = rng.random()
    if in_error and r < 0.45:
        status = rng.choice([500, 502, 503, 504])
    elif r < 0.03:
        status = rng.choice([404, 400, 401])
    else:
        status = 200
    base = rng.lognormvariate(math.log(80), 0.5)  # ~80ms median
    if in_latency:
        base *= rng.uniform(5, 8)
    if status >= 500:
        base *= 1.5
    return status, round(base, 1)


def _level(status: int) -> str:
    if status >= 500:
        return "ERROR"
    if status >= 400:
        return "WARN"
    return "INFO"


def generate(minutes: int, rate: int, seed: int):
    rng = random.Random(seed)
    ips = [f"10.0.{rng.randint(0, 4)}.{rng.randint(1, 254)}" for _ in range(60)]
    start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=minutes)
    windows = _windows(minutes)
    records, truth = [], []

    for minute in range(minutes):
        minute_start = start + timedelta(minutes=minute)
        in_traffic = minute in windows["traffic_spike"]
        in_error = minute in windows["error_burst"]
        in_latency = minute in windows["latency_spike"]
        if in_traffic or in_error or in_latency:
            kinds = [k for k, w in windows.items() if minute in w]
            truth.append({"minute": minute_start.isoformat(), "kinds": kinds})

        rpm = rate * _diurnal(minute, minutes) * rng.uniform(0.93, 1.07)
        if in_traffic:
            rpm *= 8
        count = max(0, int(rng.gauss(rpm, rpm * 0.07)))

        for _ in range(count):
            ts = minute_start + timedelta(seconds=rng.uniform(0, 60))
            status, latency = _status_and_latency(rng, in_error, in_latency)
            if status >= 500 and in_error and rng.random() < 0.6:
                message = rng.choice(ERROR_MESSAGES)
                method, path = "GET", "/api/orders"
            else:
                method, path = rng.choice(NORMAL_ROUTES)
                message = f"{method} {path}"
            records.append(
                {
                    "timestamp": ts,
                    "level": _level(status),
                    "source": "web",
                    "message": message,
                    "status": status,
                    "response_time_ms": latency,
                    "ip": rng.choice(ips),
                    "method": method,
                    "path": path,
                }
            )

    records.sort(key=lambda r: r["timestamp"])
    return records, truth


def to_json_line(rec: dict) -> str:
    out = dict(rec)
    out["timestamp"] = rec["timestamp"].isoformat()
    out.pop("method", None)
    out.pop("path", None)
    return json.dumps(out)


def to_nginx_line(rec: dict) -> str:
    ts = rec["timestamp"].strftime("%d/%b/%Y:%H:%M:%S +0000")
    size = 1024 if rec["status"] < 400 else 0
    return (
        f'{rec["ip"]} - - [{ts}] "{rec["method"]} {rec["path"]} HTTP/1.1" '
        f'{rec["status"]} {size} "-" "Mozilla/5.0" {rec["response_time_ms"] / 1000:.3f}'
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="sample_data/app_logs.jsonl")
    ap.add_argument("--format", choices=["json", "nginx"], default="json")
    ap.add_argument("--minutes", type=int, default=180)
    ap.add_argument("--rate", type=int, default=60, help="base requests/minute")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    records, truth = generate(args.minutes, args.rate, args.seed)
    emit = to_nginx_line if args.format == "nginx" else to_json_line

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(emit(r) for r in records) + "\n")

    truth_path = out_path.with_name(out_path.stem + "_truth.json")
    truth_path.write_text(json.dumps(truth, indent=2))

    print(f"Wrote {len(records)} log lines ({args.format}) to {out_path}")
    print(f"Wrote {len(truth)} anomalous minute-windows to {truth_path}")


if __name__ == "__main__":
    main()
