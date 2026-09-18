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
