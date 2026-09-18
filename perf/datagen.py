"""Data generator for the performance study (assignment Section 8.1).

Writes R(a, b) and S(b, c) as .ra relation-definition files in the engine's
own concrete syntax, so the join experiment loads them through the same
tokenizer/parser as everything else.

  a, c  -- a unique row id per tuple (just the row's index)
  b     -- the join key, drawn uniformly from a domain of size D

R.b and S.b are both drawn from {0, ..., D-1} uniformly at random. For a
fixed R tuple, the expected number of matching S tuples is then n_s / D
(S's b-values are uniform over D buckets). So the "match rate" this
generator exposes is exactly that expected-matches-per-R-tuple count, and
D is derived from it: D = max(1, round(n_s / match_rate)).
"""

import argparse
import random


def generate(n_r, n_s, match_rate, seed=0):
    rng = random.Random(seed)
    domain = max(1, round(n_s / match_rate))
    r_rows = [(i, rng.randrange(domain)) for i in range(n_r)]
    s_rows = [(rng.randrange(domain), i) for i in range(n_s)]
    return r_rows, s_rows, domain


def write_relation(path, name, attr_names, rows):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{name} ({', '.join(attr_names)}) = {{\n")
        for row in rows:
            f.write("  " + ", ".join(str(v) for v in row) + "\n")
        f.write("}\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate R(a,b)/S(b,c) test data")
    ap.add_argument("--n", type=int, required=True, help="tuples in R")
    ap.add_argument("--m", type=int, required=True, help="tuples in S")
    ap.add_argument("--match-rate", type=float, default=1.0,
                     help="expected number of S-tuples each R-tuple matches (default 1.0)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-r", required=True)
    ap.add_argument("--out-s", required=True)
    args = ap.parse_args(argv)

    r_rows, s_rows, domain = generate(args.n, args.m, args.match_rate, args.seed)
    write_relation(args.out_r, "R", ["a", "b"], r_rows)
    write_relation(args.out_s, "S", ["b", "c"], s_rows)
    print(f"wrote {args.out_r} ({args.n} tuples) and {args.out_s} ({args.m} tuples), "
          f"join-key domain size {domain} (match rate {args.match_rate})")


if __name__ == "__main__":
    main()
