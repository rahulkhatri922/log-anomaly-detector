import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { uploadLogs } from "../api/client";

// Lightweight client-side guess just for the preview; the server is authoritative.
function guessFormat(text) {
  const line = text.split("\n").find((l) => l.trim());
  if (!line) return "unknown";
  if (line.trim().startsWith("{")) return "json";
  if (/\[\d{2}\/\w{3}\/\d{4}/.test(line) && /"\w+ .* HTTP/.test(line)) return "apache / nginx";
  if (/^\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2}\s/.test(line)) return "syslog";
  return "unknown";
}

export default function Upload({ onChange }) {
  const [drag, setDrag] = useState(false);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef();
  const navigate = useNavigate();

  async function handleFile(file) {
    if (!file) return;
    setError(null);
    setResult(null);
    const head = await file.slice(0, 4000).text();
    setPreview({ name: file.name, size: file.size, format: guessFormat(head), file });
  }

  async function submit() {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      const res = await uploadLogs(preview.file);
      setResult(res);
      onChange?.();
    } catch (e) {
      setError(e.response?.data?.detail || "Upload failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1 className="page-title">Upload logs</h1>
      <p className="page-sub">
        Drop a log file — Apache/Nginx access logs, JSON structured logs, or syslog. The format is
        auto-detected; unparseable lines are skipped.
      </p>

      <div
        className={"dropzone" + (drag ? " drag" : "")}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); handleFile(e.dataTransfer.files[0]); }}
      >
        <div style={{ fontSize: 30 }}>📄</div>
        <div className="big">Drop a log file here</div>
        <div className="muted">or click to browse — .log, .jsonl, .txt</div>
        <input
          ref={inputRef}
          type="file"
          accept=".log,.jsonl,.json,.txt,text/plain"
          style={{ display: "none" }}
          onChange={(e) => handleFile(e.target.files[0])}
        />
      </div>

      {preview && !result && (
        <div className="card" style={{ marginTop: 18 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <div>
              <div style={{ fontWeight: 700 }}>{preview.name}</div>
              <div className="muted" style={{ fontSize: 13 }}>
                {(preview.size / 1024).toFixed(0)} KB · detected format:{" "}
                <span className="chip" style={{ marginLeft: 4 }}>{preview.format}</span>
              </div>
            </div>
            <button className="btn-primary" onClick={submit} disabled={busy}>
              {busy ? <>Uploading… <span className="spinner" /></> : "Parse & store"}
            </button>
          </div>
        </div>
      )}

      {error && <div className="card" style={{ marginTop: 16, borderColor: "var(--anomaly)" }}>{error}</div>}

      {result && (
        <div className="card" style={{ marginTop: 18 }}>
          <h3>Ingested ✓</h3>
          <div className="tiles">
            <div className="tile"><div className="k">Stored</div><div className="v">{result.stored.toLocaleString()}</div></div>
            <div className="tile"><div className="k">Format</div><div className="v" style={{ fontSize: 18 }}>{result.format}</div></div>
            <div className="tile"><div className="k">Skipped</div><div className="v">{result.skipped}</div></div>
          </div>
          <div className="row" style={{ marginTop: 16 }}>
            <button className="btn-primary" onClick={() => navigate("/")}>Go to dashboard →</button>
            <button onClick={() => { setResult(null); setPreview(null); }}>Upload another</button>
          </div>
        </div>
      )}
    </div>
  );
}
