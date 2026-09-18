# Relational Algebra Engine

COMP 3005 Bonus Project 1 (Fall 2026). A hand-written tokenizer, recursive
descent parser, and tree-walking evaluator for the relational algebra
language specified in the assignment. See [GRAMMAR.md](GRAMMAR.md) for the
full grammar, precedence rules, and design justification, and
[REPORT.md](REPORT.md) for the performance study.

Python 3.10+ (developed and tested on 3.13.1), standard library only for
the engine itself. `pytest` is used to run the test suite (`pip install
pytest`); nothing in `src/` imports it.

## Running it

```bash
# print a query's parse tree without executing it (no relations needed)
python ra.py --tree "project[Name](select[Age>30](Employees))"

# load a database file, run a query against it, print the result table
python ra.py --relations tests/fixtures/employees.ra --query "Emp join[Emp.DID=Dept.DID] Dept"

# a database file can end with its own query (Program ::= {RelationDef} [Query] EOF);
# in that case --query can be omitted
python ra.py --relations some_file.ra
```

Errors (lexical, syntax, name, schema, type) are printed as a single line
naming the category and, where applicable, a line:col position -- never a
Python traceback. Exit code is 1 on error, 0 on success.

## Running the tests

```bash
pip install pytest
python -m pytest tests/ -q
```

`tests/test_required_cases.py` implements the 25 numbered cases from
assignment Section 7, one test function per case (named `test_caseN_...`
so a failure maps straight back to the spec table).

## Project layout

```
GRAMMAR.md          the language's EBNF, precedence table, ambiguity demo (Section 5)
REPORT.md           the performance study (Section 8)
DESIGN_LOG.md        dated working diary, incl. AI-assistance failures
ra.py                CLI entry point
src/
  tokens.py           TokType enum, Token record
  lexer.py             hand-written scanner (no regex)
  ast_nodes.py         AST node classes for expressions and conditions
  parser.py            recursive descent parser -> AST
  relation.py           Attr / Relation: schema + tuple-set representation
  interpreter.py       evaluates an AST into a Relation; the 6 operators live here
  printer.py            parse-tree printing (--tree) and result-table printing
  errors.py             the 5 error categories, each carrying a line:col
  cli.py                argument parsing, wires the above together
perf/
  datagen.py            writes R(a,b)/S(b,c) .ra files at a chosen size/match-rate
  run_experiment.py     runs the Section 8.3 table, writes CSV results
tests/
  test_required_cases.py   the 25 required cases
  test_extra.py             additional coverage (operators, tokenizer edge cases)
  fixtures/*.ra             sample databases used by the tests
```

## What's supported

Everything in assignment Section 4: relation definitions with quoted/bare
string values and comment lines; `select`/`project`/`rename` with their
`[param](expr)` syntax; infix `union`/`intersect`/`minus`/`times`/`join[cond]`;
conditions with `and`/`or`/`not`/comparisons and qualified (`Rel.attr`)
or unqualified attribute references.

## Design decisions worth knowing for the oral check

- **Attribute qualification.** A `Relation` carries a `.name` (its current
  identity, separate from its columns) alongside its schema. `rename[X](...)`
  only changes `.name`; `times`/`join` is the one place that turns identities
  into column qualifiers, prefixing each side's still-unqualified columns
  with that side's *current* `.name`. An already-qualified column (from an
  earlier times/join) is left alone rather than re-qualified. This is what
  makes the self-join in test case 20 work: `rename[E2](Emp)` and the bare
  `Emp` on the other side of the join have different identities at the
  moment they're combined, even though both trace back to the same base
  relation. See the comment block above `_do_times` in
  [src/interpreter.py](src/interpreter.py).
- **Attribute resolution.** An unqualified reference (`Age`) matches by
  name; if more than one column shares that name (post-join, unqualified),
  it's a name error asking for qualification. A qualified reference
  (`Emp.DID`) first tries an exact qualifier+name match; if that fails and
  the qualifier equals the *relation's own current identity*, it falls back
  to matching an unqualified column of that name -- so
  `select[Employees.Age>30](Employees)` works even before any join.
- **Contextual keywords.** The lexer never emits a keyword token -- every
  word is `IDENT`. The parser only treats a word as an operator at the
  specific grammar positions where the grammar expects one (see
  GRAMMAR.md Section 2.3). This is what makes `select[union=3](R)`
  (test case 8) parse `union` as a plain attribute name.
- **Column types are inferred from data, not declared.** A relation's
  per-column type (`number`/`string`, for the union-compatibility and
  comparison type checks) is sampled from one of its own tuples rather
  than declared up front -- the language has no type annotations in
  relation headers. If a relation is empty, its column types are unknown
  and type checks against it are skipped rather than failing (nothing to
  contradict). Comparisons are type-checked dynamically, per row, rather
  than statically -- simpler, and sufficient since the language has no
  nulls or mixed-type columns to make that a real limitation.
- **`project[Name, Name](R)` is a schema error** (test case 24): the output
  would need two columns both named `Name`, which isn't a valid schema.
- **Performance-study instrumentation.** `join_compared` is incremented
  once per pair as `len(left.tuples) * len(right.tuples)`, computed
  directly rather than incremented inside the loop that builds the
  product -- both give the same exact count, but computing it directly
  avoids a second full pass over the product being mistaken for (and
  double-counted against) the pairs already generated. Attribute
  resolution inside a `Select`/`Join`'s condition is cached per
  evaluation call (see the `cache` dict threaded through `_eval_cond`)
  so that resolving `R.b`/`S.b` to column indices happens once, not once
  per billion-plus tuple pair -- a straightforward performance fix, not a
  semantic shortcut: the engine still performs the full `n * m` naive
  nested-loop comparison the assignment asks for.

## Known limitations

- Nulls and three-valued logic: out of scope per the assignment.
- No indexes, no query optimization/rewriting, no hash/sort-merge joins:
  out of scope per the assignment -- nested loops are the point.
- String ordering (`<`, `<=`, `>`, `>=` between two strings) uses Python's
  native lexicographic string ordering; the assignment doesn't specify
  this, so it's a reasonable default rather than a requirement.
- Relation/attribute redefinition inside one database file (same name used
  twice) is rejected as a schema error; the assignment doesn't test this,
  but silently shadowing felt worse than failing loudly.
