import { useCallback, useEffect, useState } from "react";
import { Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar";
import Dashboard from "./pages/Dashboard";
import Anomalies from "./pages/Anomalies";
import Upload from "./pages/Upload";
import { getStatus } from "./api/client";

export default function App() {
  const [status, setStatus] = useState(null);

  const refresh = useCallback(() => {
    getStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <div className="app">
      <Navbar status={status} />
      <div className="container">
        <Routes>
          <Route path="/" element={<Dashboard status={status} onChange={refresh} />} />
          <Route path="/anomalies" element={<Anomalies onChange={refresh} />} />
          <Route path="/upload" element={<Upload onChange={refresh} />} />
        </Routes>
      </div>
    </div>
  );
}
