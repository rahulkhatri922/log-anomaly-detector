"""Multi-format log parser.

Auto-detects and normalizes four common formats into a single ``ParsedLog``
shape: Apache (common/combined), Nginx (combined + optional ``$request_time``),
JSON structured logs, and RFC 3164 syslog.

Each line becomes: ``timestamp, level, source, message`` plus extracted fields
``status_code``, ``response_time_ms``, and ``ip`` where available.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

LEVELS = ("DEBUG", "INFO", "WARN", "ERROR", "CRITICAL")


@dataclass
class ParsedLog:
    timestamp: datetime
    level: str
    source: str
    message: str
    status_code: int | None = None
    response_time_ms: float | None = None
    ip: str | None = None
    log_format: str = "unknown"
    raw: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


# --- level helpers ------------------------------------------------------

def level_from_status(status: int | None) -> str:
    if status is None:
        return "INFO"
    if status >= 500:
        return "ERROR"
    if status >= 400:
        return "WARN"
    return "INFO"


def _normalize_level(text: str) -> str | None:
    up = text.upper()
    if "CRIT" in up or "FATAL" in up:
        return "CRITICAL"
    if "ERROR" in up or "ERR" in up or "FAIL" in up:
        return "ERROR"
    if "WARN" in up:
        return "WARN"
    if "DEBUG" in up:
        return "DEBUG"
    if "INFO" in up:
        return "INFO"
    return None


# --- Apache / Nginx access logs ----------------------------------------

_ACCESS_RE = re.compile(
    r'(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<time>[^\]]+)\]\s+'
    r'"(?P<request>[^"]*)"\s+(?P<status>\d{3})\s+(?P<size>\S+)'
    r'(?:\s+"(?P<referer>[^"]*)"\s+"(?P<agent>[^"]*)")?'
    r'(?:\s+(?P<rt>\d+\.\d+))?'
)


def _parse_access(line: str) -> ParsedLog | None:
    m = _ACCESS_RE.match(line.strip())
    if not m:
        return None
    g = m.groupdict()
    try:
        ts = datetime.strptime(g["time"], "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return None
    status = int(g["status"])
    request = g["request"] or ""
    parts = request.split()
    method, path = (parts[0], parts[1]) if len(parts) >= 2 else ("", request)
    rt_ms = float(g["rt"]) * 1000 if g.get("rt") else None
    return ParsedLog(
        timestamp=ts,
        level=level_from_status(status),
        source="web",
        message=f"{method} {path}".strip(),
        status_code=status,
        response_time_ms=rt_ms,
        ip=g["ip"],
        log_format="access",
        raw=line.rstrip("\n"),
        extra={"method": method, "path": path},
    )


# --- JSON structured logs ----------------------------------------------

_TS_KEYS = ("timestamp", "time", "@timestamp", "ts", "datetime")
_MSG_KEYS = ("message", "msg", "log", "event")
_LEVEL_KEYS = ("level", "severity", "loglevel", "lvl")
_STATUS_KEYS = ("status", "status_code", "response_status", "code")
_RT_KEYS = ("response_time_ms", "response_time", "latency_ms", "duration_ms", "elapsed_ms")
_IP_KEYS = ("ip", "client_ip", "remote_addr", "source_ip")
_SRC_KEYS = ("source", "logger", "service", "app", "component")


def _first(d: dict, keys) -> object | None:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _parse_timestamp(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # epoch seconds or milliseconds
        secs = value / 1000 if value > 1e11 else value
        return datetime.fromtimestamp(secs, tz=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _parse_json(line: str) -> ParsedLog | None:
    line = line.strip()
    if not (line.startswith("{") and line.endswith("}")):
        return None
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    ts = _parse_timestamp(_first(obj, _TS_KEYS)) or datetime.now(timezone.utc)
    status = _first(obj, _STATUS_KEYS)
    status = int(status) if status is not None and str(status).isdigit() else None
    rt = _first(obj, _RT_KEYS)
    rt_ms = float(rt) if rt is not None else None
    level_raw = _first(obj, _LEVEL_KEYS)
    level = _normalize_level(str(level_raw)) if level_raw else None
    level = level or level_from_status(status)
    return ParsedLog(
        timestamp=ts,
        level=level,
        source=str(_first(obj, _SRC_KEYS) or "app"),
        message=str(_first(obj, _MSG_KEYS) or ""),
        status_code=status,
        response_time_ms=rt_ms,
        ip=_first(obj, _IP_KEYS),
        log_format="json",
        raw=line,
        extra={k: v for k, v in obj.items() if k not in _MSG_KEYS},
    )


# --- syslog (RFC 3164) --------------------------------------------------

_SYSLOG_RE = re.compile(
    r"(?P<time>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+(?P<proc>[^:\[\s]+)(?:\[(?P<pid>\d+)\])?:\s*(?P<msg>.*)"
)


def _parse_syslog(line: str, default_year: int | None = None) -> ParsedLog | None:
    m = _SYSLOG_RE.match(line.strip())
    if not m:
        return None
    g = m.groupdict()
    year = default_year or datetime.now(timezone.utc).year
    try:
        ts = datetime.strptime(f"{year} {g['time']}", "%Y %b %d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None
    msg = g["msg"]
    return ParsedLog(
        timestamp=ts,
        level=_normalize_level(msg) or "INFO",
        source=g["proc"],
        message=msg,
        log_format="syslog",
        raw=line.rstrip("\n"),
        extra={"host": g["host"], "pid": g.get("pid")},
    )


# --- public API ---------------------------------------------------------

_PARSERS = (_parse_json, _parse_access, _parse_syslog)


def parse_line(line: str) -> ParsedLog | None:
    """Parse a single log line, trying each format. Returns None if unparseable."""
    line = line.rstrip("\n")
    if not line.strip():
        return None
    for parser in _PARSERS:
        result = parser(line)
        if result is not None:
            return result
    return None


def detect_format(text: str, sample: int = 40) -> str:
    """Guess the dominant format of a multi-line log blob."""
    counts: dict[str, int] = {}
    seen = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        parsed = parse_line(line)
        fmt = parsed.log_format if parsed else "unknown"
        counts[fmt] = counts.get(fmt, 0) + 1
        seen += 1
        if seen >= sample:
            break
    if not counts:
        return "unknown"
    return max(counts, key=counts.get)


def parse_lines(lines) -> list[ParsedLog]:
    """Parse an iterable of lines, skipping blanks and unparseable rows."""
    out = []
    for line in lines:
        parsed = parse_line(line)
        if parsed is not None:
            out.append(parsed)
    return out


def parse_text(text: str) -> list[ParsedLog]:
    return parse_lines(text.splitlines())
