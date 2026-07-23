// Display metadata for the engineered features + small formatting helpers.

export const METRICS = [
  { key: "request_count", label: "Requests / window", color: "#38bdf8", short: "req" },
  { key: "error_rate", label: "Error rate", color: "#f87171", short: "err" },
  { key: "avg_response_time_ms", label: "Avg response (ms)", color: "#fbbf24", short: "rt" },
  { key: "unique_ips", label: "Unique IPs", color: "#34d399", short: "ips" },
  { key: "ratio_5xx_2xx", label: "5xx / 2xx ratio", color: "#fb923c", short: "5xx" },
  { key: "message_entropy", label: "Message entropy", color: "#a78bfa", short: "ent" },
];

export const METRIC_LABEL = Object.fromEntries(METRICS.map((m) => [m.key, m.label]));
export const METRIC_COLOR = Object.fromEntries(METRICS.map((m) => [m.key, m.color]));

export function fmt(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return Number(v).toFixed(digits);
}

// Backend timestamps come both tz-aware ("...+00:00") and naive ("..."); treat
// them all as UTC so charts, inputs, and anomaly times line up for any viewer.
const HAS_TZ = /([Zz]|[+-]\d{2}:?\d{2})$/;
function asUtc(iso) {
  return new Date(HAS_TZ.test(iso) ? iso : iso + "Z");
}

export function shortTime(iso) {
  return asUtc(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
}

export function fullTime(iso) {
  return asUtc(iso).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
}

// Contiguous runs of anomalous windows, for shading chart regions.
export function anomalyRegions(points) {
  const regions = [];
  let start = null;
  for (let i = 0; i < points.length; i++) {
    if (points[i].is_anomaly && start === null) start = points[i].window_start;
    const ends = !points[i].is_anomaly || i === points.length - 1;
    if (start !== null && ends) {
      const end = points[i].is_anomaly ? points[i].window_start : points[i - 1].window_start;
      regions.push([start, end]);
      start = null;
    }
  }
  return regions;
}
