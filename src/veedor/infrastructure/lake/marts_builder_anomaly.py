"""Isolation Forest anomaly score for competitive processes.

One model per procurement method (distributions differ a lot between methods), fitted on the
numeric features available for that method. The score is reported separately and never feeds
the risk score. Higher means more atypical (1 - normalised average path length, as in
scikit-learn: `-score_samples`).
"""

from __future__ import annotations

from typing import Any

import duckdb
import numpy as np
import pyarrow as pa
from sklearn.ensemble import IsolationForest

from veedor.domain.signals import parameters as p

FEATURE_COLUMNS = ("log_budget", "award_to_budget", "n_tenderers", "n_enquiries", "window_days")

FEATURES_SQL = """
SELECT b.ocid, b.method,
       ln(1 + b.budget) AS log_budget,
       b.award_total / b.budget AS award_to_budget,
       CAST(b.n_tenderers AS DOUBLE) AS n_tenderers,
       CAST(b.n_enquiries AS DOUBLE) AS n_enquiries,
       w.days AS window_days
FROM base b LEFT JOIN windows w USING (ocid)
WHERE b.method_group = $competitive AND b.budget > 0 AND b.method IS NOT NULL
"""


def fit_scores(matrix: np.ndarray) -> np.ndarray:
    """Fit one Isolation Forest on `matrix` and return the anomaly score of every row."""
    model = IsolationForest(
        n_estimators=p.ANOMALY_N_ESTIMATORS, random_state=p.ANOMALY_RANDOM_STATE, n_jobs=-1
    )
    model.fit(matrix)
    return -model.score_samples(matrix)


def select_features(columns: dict[str, np.ndarray]) -> list[str]:
    """Features whose coverage in this method is high enough to be used."""
    return [
        name
        for name in FEATURE_COLUMNS
        if np.mean(~np.isnan(columns[name])) >= p.ANOMALY_MIN_FEATURE_COVERAGE
    ]


def score_method(columns: dict[str, np.ndarray]) -> tuple[np.ndarray, list[str]]:
    """Scores for one method (NaN where a used feature is missing) and the features used."""
    used = select_features(columns)
    matrix = np.column_stack([columns[name] for name in used])
    complete = ~np.isnan(matrix).any(axis=1)
    scores = np.full(matrix.shape[0], np.nan)
    if complete.sum() >= p.ANOMALY_MIN_ROWS:
        scores[complete] = fit_scores(matrix[complete])
    return scores, used


def compute_anomaly_scores(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    """Register an `anomaly(ocid, anomaly_score)` table on `con` and return a report."""
    table = con.sql(FEATURES_SQL, params={"competitive": p.COMPETITIVE_GROUP}).to_arrow_table()
    ocids = table.column("ocid").to_numpy(zero_copy_only=False)
    methods = table.column("method").to_numpy(zero_copy_only=False)
    features = {
        name: table.column(name).to_numpy(zero_copy_only=False).astype(float) for name in FEATURE_COLUMNS
    }
    out_ocid: list[np.ndarray] = []
    out_score: list[np.ndarray] = []
    report: dict[str, Any] = {}
    for method in sorted(set(methods)):
        mask = methods == method
        scores, used = score_method({k: v[mask] for k, v in features.items()})
        scored = ~np.isnan(scores)
        report[method] = {"rows": int(mask.sum()), "scored": int(scored.sum()), "features": used}
        out_ocid.append(ocids[mask][scored])
        out_score.append(scores[scored])
    ocid_all = np.concatenate(out_ocid) if out_ocid else np.array([], dtype=object)
    score_all = np.concatenate(out_score) if out_score else np.array([], dtype=float)
    result = pa.table(
        {"ocid": pa.array(ocid_all, type=pa.string()), "anomaly_score": pa.array(score_all, pa.float64())}
    )
    con.register("anomaly_arrow", result)
    con.execute("CREATE OR REPLACE TEMP TABLE anomaly AS SELECT * FROM anomaly_arrow")
    con.unregister("anomaly_arrow")
    return report
