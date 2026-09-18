"""Regenerates the REPORT.md log-log plot from the CSVs run_experiment.py
writes. Requires matplotlib (`pip install matplotlib`) -- report-only
dependency, not used anywhere in src/.

Usage: python -m perf.plot_results
"""

import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    with open(os.path.join(HERE, "results.csv")) as f:
        rows = list(csv.DictReader(f))
    ns = [int(r["n"]) for r in rows]
    ts = [float(r["wall_time_s"]) for r in rows]

    with open(os.path.join(HERE, "results.selectproject.csv")) as f:
        sp_rows = list(csv.DictReader(f))
    sel_t = [float(r["select_time_s"]) for r in sp_rows]
    proj_t = [float(r["project_time_s"]) for r in sp_rows]

    fig, ax = plt.subplots(figsize=(7, 5.5))
    ax.loglog(ns, ts, "o-", label="join (R join[R.b=S.b] S)", linewidth=2)
    ax.loglog(ns, sel_t, "s-", label="select", linewidth=2)
    ax.loglog(ns, proj_t, "^-", label="project", linewidth=2)

    ref = [ts[0] * (n / ns[0]) ** 2 for n in ns]
    ax.loglog(ns, ref, "k--", alpha=0.5, label="slope-2 reference (n^2)")

    ax.set_xlabel("n (tuples per relation)")
    ax.set_ylabel("wall time (s)")
    ax.set_title("Wall time vs n, log-log axes")
    ax.legend()
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()

    out_path = os.path.join(HERE, "time_vs_n_loglog.png")
    fig.savefig(out_path, dpi=150)
    print(f"saved {out_path}")


if __name__ == "__main__":
    main()
