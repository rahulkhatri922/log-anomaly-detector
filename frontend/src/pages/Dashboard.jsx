import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import MetricChart from "../components/MetricChart";
import { detect, getEvaluation, getTimeseries, train } from "../api/client";
import { fmt } from "../theme";

const CHARTS = [
  { key: "request_count", title: "Request count", unit: "" },
  { key: "error_rate", title: "Error rate", unit: "" },
  { key: "avg_response_time_ms", title: "Avg response time", unit: " ms" },
];

function toLocalInput(iso) {
  return iso ? iso.slice(0, 16) : "";
}

export default function Dashboard({ status, onChange }) {
  const [ts, setTs] = useState(null);
  const [evalData, setEvalData] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [busy, setBusy] = useState(null);
  const [toast, setToast] = useState(null);

  const [normalStart, setNormalStart] = useState("");
  const [normalEnd, setNormalEnd] = useState("");
  const [contamination, setContamination] = useState(0.03);

  const refresh = useCallback(() => {
    getTimeseries().then(setTs).catch(() => setTs(null));
    getEvaluation().then(setEvalData).catch(() => setEvalData(null));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  // prefill the normal range from the log range (first 35% = calm period).
  // Timestamps are naive UTC; keep the math in UTC so start/end stay consistent.
  useEffect(() => {
    const range = status?.log_range;
    if (range && !normalStart) {
      const startMs = Date.parse(range.start + "Z");
      const endMs = Date.parse(range.end + "Z");
      const normalEndMs = startMs + (endMs - startMs) * 0.35;
      setNormalStart(toLocalInput(range.start));
      setNormalEnd(new Date(normalEndMs).toISOString().slice(0, 16));
    }
  }, [status, normalStart]);

  const flash = (msg) => { setToast(msg); setTimeout(() => setToast(null), 2600); };

  async function runTrain() {
    setBusy("train");
    try {
      const res = await train({
        normal_start: normalStart || null,
        normal_end: normalEnd || null,
        contamination: Number(contamination),
      });
      flash(`Trained on ${res.n_train_windows} normal windows.`);
      onChange?.();
      refresh();
    } catch (e) {
      flash(e.response?.data?.detail || "Training failed.");
    } finally {
      setBusy(null);
    }
  }

  async function runDetect() {
    setBusy("detect");
    try {
      const res = await detect({});
      setComparison(res.comparison);
      flash(`Flagged ${res.flagged} of ${res.total_windows} windows.`);
      onChange?.();
      refresh();
    } catch (e) {
      flash(e.response?.data?.detail || "Detection failed. Train a model first.");
    } finally {
      setBusy(null);
    }
  }

  const points = ts?.points || [];
  const anomalyCount = useMemo(() => points.filter((p) => p.is_anomaly).length, [points]);

  if (status && status.log_count === 0) {
    return (
      <div className="empty">
        No logs yet. <Link to="/upload" style={{ color: "var(--accent)" }}>Upload a log file →</Link>
      </div>
    );
  }

  return (
    <div>
      <h1 className="page-title">Anomaly dashboard</h1>
      <p className="page-sub">
        Engineered per-window features over time, with anomalous windows shaded red. Train on a calm
        “normal” period, then run detection to flag the rest.
      </p>

      <div className="tiles" style={{ marginBottom: 18 }}>
        <div className="tile"><div className="k">Logs</div><div className="v">{(status?.log_count ?? 0).toLocaleString()}</div></div>
        <div className="tile"><div className="k">Windows</div><div className="v">{evalData?.total_windows ?? points.length}</div></div>
        <div className="tile"><div className="k">Anomalies</div><div className="v" style={{ color: "var(--anomaly)" }}>{evalData?.flagged_windows ?? anomalyCount}</div></div>
        <div className="tile"><div className="k">Anomaly rate</div><div className="v">{fmt((evalData?.anomaly_rate ?? 0) * 100, 1)}<small>%</small></div></div>
      </div>

      <div className="card" style={{ marginBottom: 18 }}>
        <h3>Train &amp; detect</h3>
        <div className="row" style={{ alignItems: "flex-end" }}>
          <label className="field">Normal period start
            <input type="datetime-local" value={normalStart} onChange={(e) => setNormalStart(e.target.value)} />
          </label>
          <label className="field">Normal period end
            <input type="datetime-local" value={normalEnd} onChange={(e) => setNormalEnd(e.target.value)} />
          </label>
          <label className="field">Contamination
            <input type="number" step="0.01" min="0.01" max="0.5" value={contamination} onChange={(e) => setContamination(e.target.value)} style={{ width: 90 }} />
          </label>
          <button className="btn-primary" onClick={runTrain} disabled={busy === "train"}>
            {busy === "train" ? <>Training… <span className="spinner" /></> : "Train model"}
          </button>
          <button onClick={runDetect} disabled={busy === "detect" || !status?.model_trained}>
            {busy === "detect" ? <>Detecting… <span className="spinner" /></> : "Run detection"}
          </button>
        </div>

        {status?.model && (
          <p className="muted" style={{ fontSize: 13, marginTop: 12, marginBottom: 0 }}>
            Model trained on {status.model.n_train_windows} windows · Isolation Forest
            (contamination {status.model.contamination}) + Z-score baseline · window {status.model.window_seconds}s.
          </p>
        )}
        {comparison && comparison.total_windows > 0 && (
          <div className="row" style={{ marginTop: 14, gap: 10 }}>
            <span className="chip both">both: {comparison.both}</span>
            <span className="chip iforest">isolation-forest only: {comparison.isolation_forest_only}</span>
            <span className="chip zscore">z-score only: {comparison.zscore_only}</span>
            <span className="muted" style={{ fontSize: 13 }}>agreement on flagged: {fmt(comparison.agreement_rate * 100, 0)}%</span>
          </div>
        )}
      </div>

      {points.length === 0 ? (
        <div className="empty">No feature windows to chart yet.</div>
      ) : (
        <div className="grid">
          {CHARTS.map((c) => (
            <MetricChart key={c.key} title={c.title} points={points} dataKey={c.key} color={metricColor(c.key)} unit={c.unit} />
          ))}
        </div>
      )}

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}

function metricColor(key) {
  return { request_count: "#38bdf8", error_rate: "#f87171", avg_response_time_ms: "#fbbf24" }[key] || "#38bdf8";
}
