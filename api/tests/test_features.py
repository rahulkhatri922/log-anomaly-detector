from pipeline import features, parser
from pipeline.features import FEATURE_COLUMNS

from .conftest import make_json_logs


def test_templatize_groups_numbers():
    assert features.templatize("GET /user/123") == features.templatize("GET /user/456")
    assert features.templatize("error 0xAB12") == "error #"


def test_build_features_columns_and_windows():
    logs = parser.parse_text(make_json_logs(minutes=10, rate=30, anomaly_minutes=()))
    df = features.build_features(logs, window_seconds=60)
    assert list(df.columns) == FEATURE_COLUMNS
    assert len(df) == 10
    assert (df["request_count"] > 0).all()


def test_error_rate_and_ratio_spike_in_anomaly_window():
    logs = parser.parse_text(make_json_logs(minutes=10, rate=30, anomaly_minutes=(5,)))
    df = features.build_features(logs, window_seconds=60)
    # the anomalous minute should have the highest error rate and 5xx/2xx ratio
    assert df["error_rate"].idxmax() == df.index[5]
    assert df["ratio_5xx_2xx"].iloc[5] > df["ratio_5xx_2xx"].iloc[0]


def test_request_count_jumps_on_traffic_spike():
    logs = parser.parse_text(make_json_logs(minutes=8, rate=20, anomaly_minutes=(4,)))
    df = features.build_features(logs, window_seconds=60)
    assert df["request_count"].iloc[4] > 2 * df["request_count"].iloc[0]


def test_empty_logs_returns_empty_frame():
    df = features.build_features([], window_seconds=60)
    assert df.empty
    assert list(df.columns) == FEATURE_COLUMNS


def test_features_to_records():
    logs = parser.parse_text(make_json_logs(minutes=3, rate=10, anomaly_minutes=()))
    recs = features.features_to_records(features.build_features(logs))
    assert len(recs) == 3
    assert "window_start" in recs[0]
    assert all(c in recs[0] for c in FEATURE_COLUMNS)
