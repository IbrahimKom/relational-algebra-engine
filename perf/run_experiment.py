"""Runs the Section 8.3 experiment and writes results to a CSV as it goes
(so a long run's progress survives even if it's interrupted partway).

Usage:
  python -m perf.run_experiment --out results.csv
  python -m perf.run_experiment --out results.csv --sizes 1000,2000,4000
  python -m perf.run_experiment --out results.csv --match-rate 5
"""

import argparse
import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from perf.datagen import generate, write_relation
from src.parser import parse_program, parse_query
from src.lexer import Lexer
from src.interpreter import build_environment, evaluate, COUNTERS

DEFAULT_SIZES = [1000, 2000, 4000, 8000, 16000, 32000, 64000]


def _tokenize(s):
    return Lexer(s).tokenize()


def run_one_join(n, m, match_rate, seed, tmp_dir):
    r_rows, s_rows, domain = generate(n, m, match_rate, seed)
    r_path = os.path.join(tmp_dir, f"R_{n}.ra")
    s_path = os.path.join(tmp_dir, f"S_{m}.ra")
    write_relation(r_path, "R", ["a", "b"], r_rows)
    write_relation(s_path, "S", ["b", "c"], s_rows)

    with open(r_path, encoding="utf-8") as f:
        r_defs, _ = parse_program(_tokenize(f.read()))
    with open(s_path, encoding="utf-8") as f:
        s_defs, _ = parse_program(_tokenize(f.read()))
    env = build_environment(r_defs + s_defs)

    query_ast = parse_query(_tokenize("R join[R.b=S.b] S"))

    COUNTERS["select_examined"] = 0
    COUNTERS["join_compared"] = 0
    t0 = time.perf_counter()
    result = evaluate(query_ast, env)
    elapsed = time.perf_counter() - t0

    return {
        "n": n, "m": m,
        "comparisons": COUNTERS["join_compared"],
        "wall_time_s": elapsed,
        "output_tuples": len(result.tuples),
        "domain": domain,
    }


def run_select_project(n, tmp_dir, seed):
    """Same-size select/project timing for Section 8.3's comparison sub-study."""
    r_rows, _, _ = generate(n, n, 1.0, seed)
    r_path = os.path.join(tmp_dir, f"SP_{n}.ra")
    write_relation(r_path, "R", ["a", "b"], r_rows)
    with open(r_path, encoding="utf-8") as f:
        r_defs, _ = parse_program(_tokenize(f.read()))
    env = build_environment(r_defs)

    select_ast = parse_query(_tokenize("select[b=0](R)"))
    COUNTERS["select_examined"] = 0
    t0 = time.perf_counter()
    sel_result = evaluate(select_ast, env)
    select_time = time.perf_counter() - t0
    select_examined = COUNTERS["select_examined"]

    project_ast = parse_query(_tokenize("project[b](R)"))
    t0 = time.perf_counter()
    evaluate(project_ast, env)
    project_time = time.perf_counter() - t0

    return {
        "n": n,
        "select_examined": select_examined,
        "select_time_s": select_time,
        "select_output": len(sel_result.tuples),
        "project_time_s": project_time,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run the Section 8 performance study")
    ap.add_argument("--out", required=True, help="join-results CSV path")
    ap.add_argument("--sp-out", default=None,
                     help="select/project results CSV path (default: <out>.selectproject.csv)")
    ap.add_argument("--sizes", default=None,
                     help="comma-separated sizes (default: 1000,2000,4000,8000,16000,32000,64000)")
    ap.add_argument("--match-rate", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--tmp-dir", default=None)
    args = ap.parse_args(argv)

    sizes = [int(x) for x in args.sizes.split(",")] if args.sizes else DEFAULT_SIZES
    tmp_dir = args.tmp_dir or os.path.join(os.path.dirname(args.out) or ".", "_perf_data")
    os.makedirs(tmp_dir, exist_ok=True)
    sp_out = args.sp_out or (os.path.splitext(args.out)[0] + ".selectproject.csv")

    fieldnames = ["n", "m", "comparisons", "wall_time_s", "output_tuples", "domain"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for n in sizes:
            print(f"[join] n=m={n} match_rate={args.match_rate} ...", flush=True)
            row = run_one_join(n, n, args.match_rate, args.seed, tmp_dir)
            writer.writerow(row)
            f.flush()
            print(f"  -> comparisons={row['comparisons']:,} "
                  f"time={row['wall_time_s']:.4f}s output={row['output_tuples']:,}",
                  flush=True)

    sp_fields = ["n", "select_examined", "select_time_s", "select_output", "project_time_s"]
    with open(sp_out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=sp_fields)
        writer.writeheader()
        for n in sizes:
            print(f"[select/project] n={n} ...", flush=True)
            row = run_select_project(n, tmp_dir, args.seed)
            writer.writerow(row)
            f.flush()
            print(f"  -> select_time={row['select_time_s']:.4f}s "
                  f"project_time={row['project_time_s']:.4f}s", flush=True)

    print(f"done. wrote {args.out} and {sp_out}")


if __name__ == "__main__":
    main()
