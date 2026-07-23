import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "/api",
});

export const getStatus = () => api.get("/status").then((r) => r.data);

export const uploadLogs = (file) => {
  const form = new FormData();
  form.append("file", file);
  return api
    .post("/logs/upload", form, { headers: { "Content-Type": "multipart/form-data" } })
    .then((r) => r.data);
};

export const train = (body) => api.post("/train", body).then((r) => r.data);
export const detect = (body) => api.post("/detect", body).then((r) => r.data);
export const getAnomalies = (params) => api.get("/anomalies", { params }).then((r) => r.data);
export const labelAnomaly = (id, label) =>
  api.post(`/anomalies/${id}/label`, { label }).then((r) => r.data);
export const getTimeseries = (params) =>
  api.get("/metrics/timeseries", { params }).then((r) => r.data);
export const getEvaluation = () => api.get("/evaluation").then((r) => r.data);

export default api;
