import pytest

from pipeline import features, ml, parser

from .conftest import make_json_logs


def _features(anomaly_minutes=(20, 21, 22)):
    logs = parser.parse_text(make_json_logs(minutes=30, rate=40, anomaly_minutes=anomaly_minutes))
    return features.build_features(logs, window_seconds=60)


def test_train_returns_bundle():
    bundle = ml.train(_features(anomaly_minutes=()), window_seconds=60, contamination=0.05)
    assert bundle.n_train_windows == 30
    assert set(bundle.baseline_mean) == set(features.FEATURE_COLUMNS)
    assert "window_seconds" in bundle.summary()


def test_train_needs_two_windows():
    with pytest.raises(ValueError):
        ml.train(_features().iloc[:1])


def test_detect_flags_the_injected_anomaly():
    normal = _features(anomaly_minutes=())
    bundle = ml.train(normal, window_seconds=60, contamination=0.05)
    full = _features(anomaly_minutes=(20, 21, 22))
    detected = ml.detect(full, bundle, z_threshold=3.0)
    flagged = detected[detected["is_anomaly"]]
    flagged_minutes = {ts.minute for ts in flagged.index}
    # at least one of the injected minutes is caught
    assert flagged_minutes & {20, 21, 22}
    # anomaly windows should carry which metrics tripped
    a_row = detected.loc[detected.index[20]]
    assert isinstance(a_row["triggered_metrics"], list)
    assert a_row["agreement"] in {"both", "isolation_forest_only", "zscore_only", "none"}


def test_zscore_triggers_on_error_rate():
    normal = _features(anomaly_minutes=())
    bundle = ml.train(normal, window_seconds=60)
    full = _features(anomaly_minutes=(20,))
    detected = ml.detect(full, bundle, z_threshold=3.0)
    assert detected.loc[detected.index[20], "zscore_flag"]


def test_comparison_summary():
    normal = _features(anomaly_minutes=())
    bundle = ml.train(normal)
    detected = ml.detect(_features(anomaly_minutes=(20, 21)), bundle)
    summary = ml.comparison_summary(detected)
    assert summary["total_windows"] == 30
    assert "agreement_rate" in summary
    assert summary["either"] >= summary["both"]


def test_evaluate_precision_recall_f1():
    pred = [True, True, False, False]
    true = [True, False, False, True]
    result = ml.evaluate(pred, true)
    assert result["true_positives"] == 1
    assert result["false_positives"] == 1
    assert result["false_negatives"] == 1
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["f1"] == 0.5


def test_evaluate_length_mismatch():
    with pytest.raises(ValueError):
        ml.evaluate([True], [True, False])


def test_save_and_load_bundle(tmp_path):
    bundle = ml.train(_features(anomaly_minutes=()))
    path = tmp_path / "m.joblib"
    ml.save_bundle(bundle, path)
    loaded = ml.load_bundle(path)
    assert loaded.n_train_windows == bundle.n_train_windows
    assert loaded.feature_columns == bundle.feature_columns


def test_detect_empty_features_returns_empty():
    bundle = ml.train(_features(anomaly_minutes=()))
    assert ml.detect(features.build_features([]), bundle).empty
