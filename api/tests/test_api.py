import io


def _upload(client, text):
    return client.post(
        "/api/logs/upload",
        files={"file": ("app.jsonl", io.BytesIO(text.encode()), "text/plain")},
    )


def test_health_and_empty_status(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    status = client.get("/api/status").json()
    assert status["log_count"] == 0
    assert status["model_trained"] is False


def test_upload_logs(client, sample_logs):
    resp = _upload(client, sample_logs)
    assert resp.status_code == 200
    body = resp.json()
    assert body["stored"] > 0
    assert body["format"] == "json"
    assert client.get("/api/status").json()["log_count"] == body["stored"]


def test_upload_unparseable_rejected(client):
    resp = _upload(client, "garbage line 1\nnonsense line 2\n")
    assert resp.status_code == 422


def test_train_requires_logs(client):
    resp = client.post("/api/train", json={})
    assert resp.status_code == 400


def test_detect_requires_model(client, sample_logs):
    _upload(client, sample_logs)
    assert client.post("/api/detect", json={}).status_code == 400


def test_full_flow_upload_train_detect(client, sample_logs):
    _upload(client, sample_logs)

    train = client.post("/api/train", json={"contamination": 0.05, "window_seconds": 60})
    assert train.status_code == 200
    assert train.json()["n_train_windows"] >= 2

    detect = client.post("/api/detect", json={"z_threshold": 3.0})
    assert detect.status_code == 200
    body = detect.json()
    assert body["total_windows"] > 0
    assert body["flagged"] >= 1
    assert "agreement_rate" in body["comparison"]

    anomalies = client.get("/api/anomalies").json()["anomalies"]
    assert len(anomalies) == body["flagged"]
    first = anomalies[0]
    assert {"window_start", "iforest_score", "detectors", "abnormal_features"} <= first.keys()


def test_label_and_evaluation(client, sample_logs):
    _upload(client, sample_logs)
    client.post("/api/train", json={})
    client.post("/api/detect", json={})
    anomalies = client.get("/api/anomalies").json()["anomalies"]
    assert anomalies

    label = client.post(f"/api/anomalies/{anomalies[0]['id']}/label", json={"label": "true_positive"})
    assert label.status_code == 200
    assert label.json()["label"] == "true_positive"

    # filter by label
    tp = client.get("/api/anomalies?label=true_positive").json()["anomalies"]
    assert len(tp) == 1

    evaluation = client.get("/api/evaluation").json()
    assert evaluation["true_positives"] == 1
    assert evaluation["anomaly_rate"] > 0
    assert evaluation["precision"] == 1.0


def test_label_bad_value_and_missing(client, sample_logs):
    _upload(client, sample_logs)
    client.post("/api/train", json={})
    client.post("/api/detect", json={})
    assert client.post("/api/anomalies/999999/label", json={"label": "true_positive"}).status_code == 404
    aid = client.get("/api/anomalies").json()["anomalies"][0]["id"]
    assert client.post(f"/api/anomalies/{aid}/label", json={"label": "maybe"}).status_code == 422


def test_timeseries(client, sample_logs):
    _upload(client, sample_logs)
    client.post("/api/train", json={})
    client.post("/api/detect", json={})
    ts = client.get("/api/metrics/timeseries").json()
    assert ts["window_seconds"] == 60
    assert len(ts["points"]) > 0
    assert any(p["is_anomaly"] for p in ts["points"])
    assert "error_rate" in ts["points"][0]


def test_detect_reruns_preserve_labels(client, sample_logs):
    _upload(client, sample_logs)
    client.post("/api/train", json={})
    client.post("/api/detect", json={})
    aid = client.get("/api/anomalies").json()["anomalies"][0]["id"]
    client.post(f"/api/anomalies/{aid}/label", json={"label": "false_positive"})
    # re-run detection; the label on that window should survive
    client.post("/api/detect", json={})
    labels = [a["label"] for a in client.get("/api/anomalies").json()["anomalies"]]
    assert "false_positive" in labels
