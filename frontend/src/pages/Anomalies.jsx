import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getAnomalies, getEvaluation, labelAnomaly } from "../api/client";
import { METRIC_LABEL, fmt, fullTime } from "../theme";

const AGREEMENT_LABEL = {
  both: "both detectors",
  isolation_forest_only: "isolation forest",
  zscore_only: "z-score",
};

export default function Anomalies({ onChange }) {
  const [anomalies, setAnomalies] = useState([]);
  const [evalData, setEvalData] = useState(null);
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    setLoading(true);
    Promise.all([getAnomalies(), getEvaluation()])
      .then(([a, e]) => { setAnomalies(a.anomalies); setEvalData(e); })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  async function label(id, value) {
    const updated = await labelAnomaly(id, value);
    setAnomalies((prev) => prev.map((a) => (a.id === id ? updated : a)));
    getEvaluation().then(setEvalData);
    onChange?.();
  }

  const shown = useMemo(() => {
    if (filter === "all") return anomalies;
    return anomalies.filter((a) => a.agreement === filter);
  }, [anomalies, filter]);

  return (
    <div>
      <h1 className="page-title">Detected anomalies</h1>
      <p className="page-sub">
        Each flagged window shows which detector(s) fired and which features were abnormal. Label
        them true/false positive to build a labeled dataset and measure precision.
      </p>

      {evalData && <EvaluationPanel data={evalData} />}

      <div className="row" style={{ margin: "20px 0 14px" }}>
        {["all", "both", "isolation_forest_only", "zscore_only"].map((f) => (
          <button key={f} onClick={() => setFilter(f)} className={filter === f ? "btn-primary" : ""}>
            {f === "all" ? "All" : AGREEMENT_LABEL[f]}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="muted"><span className="spinner" /> Loading…</p>
      ) : shown.length === 0 ? (
        <div className="empty">
          No anomalies{filter !== "all" ? " for this filter" : ""}.{" "}
          {anomalies.length === 0 && (
            <Link to="/" style={{ color: "var(--accent)" }}>Train &amp; run detection →</Link>
          )}
        </div>
      ) : (
        <div className="grid">
          {shown.map((a) => (
            <AnomalyCard key={a.id} a={a} onLabel={label} />
          ))}
        </div>
      )}
    </div>
  );
}

function EvaluationPanel({ data }) {
  return (
    <div className="card">
      <h3>Evaluation</h3>
      <div className="tiles">
        <div className="tile"><div className="k">Anomaly rate</div><div className="v">{fmt(data.anomaly_rate * 100, 1)}<small>%</small></div></div>
        <div className="tile"><div className="k">Flagged</div><div className="v">{data.flagged_windows}<small> / {data.total_windows}</small></div></div>
        <div className="tile"><div className="k">Labeled</div><div className="v">{data.labeled}</div></div>
        <div className="tile"><div className="k">Precision</div><div className="v">{data.precision === null ? "—" : fmt(data.precision, 2)}</div></div>
      </div>
      <p className="muted" style={{ fontSize: 13, margin: "12px 0 0" }}>{data.note}</p>
    </div>
  );
}

function AnomalyCard({ a, onLabel }) {
  return (
    <div className={"anomaly-item " + a.agreement}>
      <div className="anomaly-head">
        <span className="anomaly-time">{fullTime(a.window_start)}</span>
        {a.detectors.includes("isolation_forest") && <span className="chip iforest">iforest {fmt(a.iforest_score, 3)}</span>}
        {a.detectors.includes("zscore") && <span className="chip zscore">z-score {fmt(a.max_abs_z, 1)}σ</span>}
        {a.agreement === "both" && <span className="chip both">both agree</span>}
        <span style={{ marginLeft: "auto" }} />
        {a.label ? (
          <span className={"label-tag " + (a.label === "true_positive" ? "tp" : "fp")}>
            {a.label === "true_positive" ? "✓ true positive" : "✗ false positive"}
          </span>
        ) : (
          <>
            <button className="btn-good" onClick={() => onLabel(a.id, "true_positive")}>True positive</button>
            <button className="btn-bad" onClick={() => onLabel(a.id, "false_positive")}>False positive</button>
          </>
        )}
      </div>

      {a.abnormal_features.length > 0 && (
        <div className="feat-badges">
          {a.abnormal_features.map((f) => (
            <span className="feat-badge" key={f.metric}>
              {METRIC_LABEL[f.metric] || f.metric}: {f.value} <b>({f.z > 0 ? "+" : ""}{fmt(f.z, 1)}σ)</b>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
