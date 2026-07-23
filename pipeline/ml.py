"""Anomaly detectors: Isolation Forest + a Z-score statistical detector.

Two complementary approaches:

* **Isolation Forest** (scikit-learn) learns the shape of "normal" from a
  training period and flags windows that are easy to isolate.
* **Z-score** flags any window whose metric drifts more than ``threshold``
  standard deviations from the training baseline — cheap, interpretable, and a
  good sanity check on the model.

``detect`` runs both and reports agreement so you can see where a learned model
and simple statistics agree or diverge.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from .features import FEATURE_COLUMNS


@dataclass
class ModelBundle:
    iforest: IsolationForest
    scaler: StandardScaler
    feature_columns: list
    baseline_mean: dict
    baseline_std: dict
    window_seconds: int
    contamination: float
    n_train_windows: int
    trained_at: str
    normal_range: dict = field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "trained_at": self.trained_at,
            "window_seconds": self.window_seconds,
            "contamination": self.contamination,
            "n_train_windows": self.n_train_windows,
            "feature_columns": self.feature_columns,
            "baseline_mean": {k: round(v, 3) for k, v in self.baseline_mean.items()},
            "baseline_std": {k: round(v, 3) for k, v in self.baseline_std.items()},
            "normal_range": self.normal_range,
        }


def train(
    features: pd.DataFrame,
    window_seconds: int = 60,
    contamination: float = 0.05,
    normal_range: dict | None = None,
) -> ModelBundle:
    """Fit an Isolation Forest and record the Z-score baseline on normal data."""
    if len(features) < 2:
        raise ValueError("Need at least 2 feature windows to train.")

    X = features[FEATURE_COLUMNS].to_numpy(dtype=float)
    scaler = StandardScaler().fit(X)
    iforest = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        random_state=42,
    ).fit(scaler.transform(X))

    return ModelBundle(
        iforest=iforest,
        scaler=scaler,
        feature_columns=list(FEATURE_COLUMNS),
        baseline_mean={c: float(features[c].mean()) for c in FEATURE_COLUMNS},
        baseline_std={c: float(features[c].std(ddof=0)) for c in FEATURE_COLUMNS},
        window_seconds=window_seconds,
        contamination=contamination,
        n_train_windows=int(len(features)),
        trained_at=datetime.now(timezone.utc).isoformat(),
        normal_range=normal_range or {},
    )


def _zscore_matrix(features: pd.DataFrame, bundle: ModelBundle) -> pd.DataFrame:
    """Per-metric signed z-scores vs the training baseline (0 where std==0)."""
    z = pd.DataFrame(index=features.index)
    for col in bundle.feature_columns:
        std = bundle.baseline_std.get(col, 0.0)
        mean = bundle.baseline_mean.get(col, 0.0)
        if std and std > 1e-9:
            z[col] = (features[col] - mean) / std
        else:
            z[col] = 0.0
    return z


def detect(
    features: pd.DataFrame,
    bundle: ModelBundle,
    z_threshold: float = 3.0,
) -> pd.DataFrame:
    """Run both detectors over ``features`` and return an annotated frame."""
    if features.empty:
        return pd.DataFrame()

    X = features[bundle.feature_columns].to_numpy(dtype=float)
    Xs = bundle.scaler.transform(X)
    iforest_flag = bundle.iforest.predict(Xs) == -1
    # decision_function: lower = more anomalous. Flip so higher = more anomalous.
    iforest_score = -bundle.iforest.decision_function(Xs)

    z = _zscore_matrix(features, bundle)
    abs_z = z.abs()
    zscore_flag = (abs_z > z_threshold).any(axis=1)

    out = features.copy()
    out["iforest_score"] = np.round(iforest_score, 4)
    out["iforest_flag"] = iforest_flag
    out["zscore_flag"] = zscore_flag.to_numpy()
    out["max_abs_z"] = np.round(abs_z.max(axis=1).to_numpy(), 3)

    triggered, abnormal, detectors, agreement = [], [], [], []
    for i, (_, zrow) in enumerate(z.iterrows()):
        trig = [c for c in bundle.feature_columns if abs(zrow[c]) > z_threshold]
        triggered.append(trig)
        ranked = sorted(bundle.feature_columns, key=lambda c: abs(zrow[c]), reverse=True)
        abnormal.append(
            [
                {"metric": c, "value": round(float(features.iloc[i][c]), 3), "z": round(float(zrow[c]), 2)}
                for c in ranked[:3]
                if abs(zrow[c]) > 1.5
            ]
        )
        d = []
        if iforest_flag[i]:
            d.append("isolation_forest")
        if zscore_flag.iloc[i]:
            d.append("zscore")
        detectors.append(d)
        if iforest_flag[i] and zscore_flag.iloc[i]:
            agreement.append("both")
        elif iforest_flag[i]:
            agreement.append("isolation_forest_only")
        elif zscore_flag.iloc[i]:
            agreement.append("zscore_only")
        else:
            agreement.append("none")

    out["triggered_metrics"] = triggered
    out["abnormal_features"] = abnormal
    out["detectors"] = detectors
    out["agreement"] = agreement
    out["is_anomaly"] = out["iforest_flag"] | out["zscore_flag"]
    return out


def comparison_summary(detected: pd.DataFrame) -> dict:
    """How often the two detectors agree, for the comparison view."""
    if detected.empty:
        return {"total_windows": 0}
    counts = detected["agreement"].value_counts().to_dict()
    total = len(detected)
    both = counts.get("both", 0)
    either = int((detected["is_anomaly"]).sum())
    return {
        "total_windows": total,
        "isolation_forest_flagged": int(detected["iforest_flag"].sum()),
        "zscore_flagged": int(detected["zscore_flag"].sum()),
        "both": both,
        "isolation_forest_only": counts.get("isolation_forest_only", 0),
        "zscore_only": counts.get("zscore_only", 0),
        "either": either,
        # agreement over the union of flagged windows
        "agreement_rate": round(both / either, 3) if either else 1.0,
    }


def evaluate(pred_flags, true_labels) -> dict:
    """Precision / recall / F1 given predicted flags and ground-truth labels."""
    pred = np.asarray(pred_flags, dtype=bool)
    true = np.asarray(true_labels, dtype=bool)
    if len(pred) != len(true):
        raise ValueError("pred_flags and true_labels must be the same length.")
    tp = int(np.sum(pred & true))
    fp = int(np.sum(pred & ~true))
    fn = int(np.sum(~pred & true))
    tn = int(np.sum(~pred & ~true))
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "true_negatives": tn,
        "n_labeled": int(len(true)),
    }


# --- persistence --------------------------------------------------------

def save_bundle(bundle: ModelBundle, path) -> None:
    import joblib

    joblib.dump(bundle, path)


def load_bundle(path) -> ModelBundle:
    import joblib

    return joblib.load(path)
