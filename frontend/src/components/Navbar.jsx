import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/anomalies", label: "Anomalies" },
  { to: "/upload", label: "Upload" },
];

export default function Navbar({ status }) {
  const trained = status?.model_trained;
  const logs = status?.log_count ?? 0;
  return (
    <nav className="nav">
      <div className="nav-inner">
        <NavLink to="/" className="brand">
          <span className="pulse" /> Log Anomaly Detector
        </NavLink>
        {links.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            end={l.end}
            className={({ isActive }) => "link" + (isActive ? " active" : "")}
          >
            {l.label}
          </NavLink>
        ))}
        <span className="status-pill">
          <span><span className="dot on" style={{ background: "#38bdf8" }} />{logs.toLocaleString()} logs</span>
          <span>
            <span className={"dot " + (trained ? "on" : "off")} />
            {trained ? "model trained" : "no model"}
          </span>
        </span>
      </div>
    </nav>
  );
}
