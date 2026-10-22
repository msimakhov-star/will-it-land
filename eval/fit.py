"""Fit land_score weights against YouGov fame, using the rows saved by eval/kill_test.py.

Model: fame_gen ~ w0 + w1 * popularity + w2 * age_affinity(gen).  Plain least squares, no numpy.
Prints the fitted weights and the Spearman before/after so you can decide whether to move them into
server/pipeline.py (land_score). Run after kill_test: python -m eval.fit
"""
from __future__ import annotations

import json
import os

from eval.kill_test import GEN_BUCKETS, OUT, spearman
from server import qloo


def lstsq(X: list[list[float]], y: list[float]) -> list[float]:
    """Solve (X^T X) w = X^T y by Gaussian elimination."""
    n = len(X[0])
    A = [[sum(X[k][i] * X[k][j] for k in range(len(X))) for j in range(n)] for i in range(n)]
    b = [sum(X[k][i] * y[k] for k in range(len(X))) for i in range(n)]
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(A[r][i]))
        A[i], A[p], b[i], b[p] = A[p], A[i], b[p], b[i]
        for r in range(i + 1, n):
            f = A[r][i] / A[i][i]
            for c in range(i, n):
                A[r][c] -= f * A[i][c]
            b[r] -= f * b[i]
    w = [0.0] * n
    for i in range(n - 1, -1, -1):
        w[i] = (b[i] - sum(A[i][c] * w[c] for c in range(i + 1, n))) / A[i][i]
    return w


def main():
    rows = json.load(open(os.path.join(OUT, "kill_test_rows.json")))
    rows = [r for r in rows if r.get("qloo_id")]
    demo = qloo.demographics([r["qloo_id"] for r in rows])  # cached from the kill test
    X, y = [], []
    for r in rows:
        age = demo.get(r["qloo_id"], {}).get("age") or {}
        for gen, buckets in GEN_BUCKETS.items():
            aff = sum(float(age.get(b, 0) or 0) for b in buckets) / len(buckets)
            X.append([1.0, float(r["qloo_pop"] or 0), aff])
            y.append(float(r[f"fame_{gen}"]))
    w = lstsq(X, y)
    print(f"fame ~ {w[0]:.1f} + {w[1]:.1f} * popularity + {w[2]:.1f} * age_affinity   (current land_score: 0 + 100 * popularity + 35 * age_affinity)")
    pred_old = [100 * x[1] + 35 * x[2] for x in X]
    pred_new = [w[0] + w[1] * x[1] + w[2] * x[2] for x in X]
    print(f"spearman vs fame, pooled over generations: current {spearman(pred_old, y):.3f}  fitted {spearman(pred_new, y):.3f}")
    # the gap is what an audience switch changes
    gap_t, gap_o, gap_n = [], [], []
    for i in range(0, len(X), len(GEN_BUCKETS)):
        m, b = i, i + list(GEN_BUCKETS).index("babyboomers")
        gap_t.append(y[m] - y[b]); gap_o.append(pred_old[m] - pred_old[b]); gap_n.append(pred_new[m] - pred_new[b])
    print(f"spearman on millennial-minus-boomer gap: current {spearman(gap_o, gap_t):.3f}  fitted {spearman(gap_n, gap_t):.3f}")


if __name__ == "__main__":
    assert [round(v, 6) for v in lstsq([[1, 0], [1, 1], [1, 2]], [1, 3, 5])] == [1.0, 2.0]
    main()
