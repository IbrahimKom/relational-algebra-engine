# DESIGN_LOG.md

Dated diary of working sessions. Each entry: what I was trying to do, what
I tried, what broke. AI-assistance failures are called out specifically
(symptom, why it was wrong, how I found it) per the assignment's
requirement of at least three such entries.

> Note to self for the oral check: I need to be able to explain every line
> in `src/`, not just the fact that Claude wrote it. Before submitting,
> re-read each file cold and make sure I can walk through it without notes.

---

## 2026-09-17 — Grammar design, day 1

**Goal:** get GRAMMAR.md into a first complete draft before writing any
code, per the assignment's explicit instruction ("almost every painful bug
in this project comes from a grammar that was never written down").

**What I did:**
- Read the assignment spec (Section 4) closely to pin down the exact
  concrete syntax: unary ops (`select`/`project`/`rename`) take
  `[param](expr)`, binary ops are infix, conditions are `=`/`!=`/`<`/`<=`/
  `>`/`>=` combined with `and`/`or`/`not`.
- Decided the precedence table for the six relational operators by analogy
  to arithmetic: `union`/`minus` at the bottom (same tier, left-assoc,
  because `minus` isn't associative — same reason `-` isn't), `intersect`
  above them (distributes over `union` like `*` over `+`), `times`/`join`
  at the top (most "primary" combination of two relations).
- Worked the required ambiguity demo for `A union B minus C` against the
  naive grammar in the assignment: found `A(X)={1}, B(X)={1}, C(X)={1}`
  gives `{}` under one bracketing and `{1}` under the other — a clean,
  minimal witness that the naive grammar is genuinely ambiguous, not just
  syntactically iffy.
- Decided the "soft keyword" rule for case 8 (`select[union=3](R)`):
  the tokenizer never special-cases keyword spellings; the parser only
  treats a word as an operator keyword at the specific grammar positions
  where an operator is expected next. An `Operand` inside a `Comparison`
  is always an identifier, so `union` as a column name just works.

**AI assistance issue #1 (caught immediately, before it reached code):**
Claude's first draft of the stratified grammar named the union/minus rule
`SetLevel` and the times/join rule `IntersectLevel`, with the tiers wired
so the naming didn't match which operator each rule actually parsed — it
had named each rule after what it *consumes as input* (its operand) rather
than the operator it parses, then papered over the mismatch with an
after-the-fact "naming note" instead of just renaming the rules correctly.
I made Claude fix it before anything downstream depended on the wrong
names: `SetLevel` (union/minus) → built from `IntersectLevel` (intersect)
→ built from `ProductLevel` (times/join) → built from `Primary`. Lesson:
check that grammar rule names actually describe what they parse before
trusting a generated EBNF draft, especially once precedence tiers start
nesting three or four deep — a plausible-looking rule name is not the same
as a correct one.

**Next:** tokenizer (assignment cases 1–9), then parser + tree printer
(cases 10–17).

---

## 2026-09-17 — Tokenizer, parser, operators, errors, all 25 cases passing

**Goal:** get the full pipeline (lexer → parser → AST → tree printer →
interpreter → CLI) working end to end against every case in Section 7,
following the grammar from the previous entry rule-for-rule.

**What I did:**
- Built the lexer (`src/lexer.py`) as a plain character scanner: no regex,
  maximal munch handled explicitly for `>=`/`<=`/`!=` (peek one char ahead
  before deciding) and for negative numbers (`-` only starts a NUMBER if
  immediately followed by a digit — otherwise it's a lexical error, since
  this language has no subtraction operator to confuse it with).
- Built the parser (`src/parser.py`) as one function per grammar rule from
  GRAMMAR.md, using the iterative "operand, then loop" shape everywhere a
  binary operator sits, per the left-recursion-removal argument from
  Section 4 of that doc.
- Implemented the six operators in `src/interpreter.py`. The one genuinely
  hard design call was how attribute qualification works across
  rename/times/join (documented in README.md "Qualification model" and as
  a comment above `_do_times`): a `Relation` carries a `.name` identity
  separate from its columns; `times`/`join` is the only place that turns
  an identity into a column prefix. Verified this against the self-join
  test case (20) directly, since that's the case that only works if this
  model is right.
- Verified all 25 required cases via a quick `--tree`/`--query` smoke pass
  on the CLI before writing the pytest suite, then locked them in as
  `tests/test_required_cases.py` (26 tests: the 25 cases, with case 11
  split into "grouping matches the documented rule" + "a concrete data
  instance where the other grouping disagrees", as the assignment asks
  for both). Added `tests/test_extra.py` for operators/paths the 25 cases
  don't each individually hit (bare `times`, `intersect`, relation
  redefinition, comment/blank-line handling in a tuple block, a relation
  literally named `union`).

**AI assistance issue #2:** first draft of the join instrumentation
(Section 8.2's "increment once for every pair your join compares")
incremented a counter once inside `_do_times` while building the cross
product, *and* incremented it again in a second loop filtering the
product by the join condition — double-counting every pair. Caught by
reading the two loops side by side before ever running a real experiment,
not by a failing test (nothing was asserting on the counter's value yet).
Fixed by computing `len(left.tuples) * len(right.tuples)` directly once,
in the one place (`Join` evaluation) that's semantically "the join", and
removing the increment from the generic `_do_times` helper (which is also
used by bare `times`, which shouldn't count as a "join comparison" at
all). Lesson: an instrumentation counter that's incremented in more than
one place for what's conceptually a single event is a red flag worth
checking by hand, since a test suite built before any real data exists
can't catch a wrong-but-self-consistent count.

**AI assistance issue #3:** the first working version of `--tree` crashed
with `UnicodeEncodeError` on Windows (`cp1252` codec can't encode the
box-drawing characters `└`/`├`/`│` the tree printer uses) — Claude's draft
never considered that Windows consoles don't default to UTF-8 stdout.
This one only showed up by actually running the CLI, exactly the kind of
gap "run your own code" is supposed to surface. Fixed with an explicit
`stream.reconfigure(encoding="utf-8")` on stdout/stderr at CLI startup.

**Next:** performance study — data generator, instrumentation is already
wired in from issue #2, then the Section 8.3 experiment table.

---

## 2026-09-18 — Performance run blew up memory; fixed the join implementation

**Goal:** run the real Section 8.3 experiment (1000→64000 tuples) in the
background and fill in REPORT.md.

**What happened:** the background run finished n=1000/2000/4000/8000 on
schedule (matching the earlier small-scale estimate of ~1.3–1.5μs per
comparison), then went completely silent partway through n=16000 -- no
progress for over an hour. Checked `tasklist`: the python process was
still alive, but sitting at **8.26 GB of RAM** and climbing. Killed it
before it got to 32000/64000, where the same bug would have needed
tens of gigabytes.

**AI assistance issue #4 (the big one):** `join[c]` is defined in the spec
as "times followed by select[c]", and Claude's first implementation took
that literally -- `_do_times()` built the *entire* cross product as a
materialized Python `set` of concatenated tuples, and only then filtered
it by the condition. That's fine semantically (same result), but at
n=m=16000 that's 256,000,000 tuples held in memory *simultaneously*
before a single one gets discarded -- and at n=m=64000 it would have been
4.1 billion. This is a real memory-blowup bug, not just "slow because
nested loops," and it only showed up by actually running the experiment
at a size big enough to hit it -- nothing in the 25 correctness test
cases (all tiny relations) or a code read would have caught it, since the
code is *correct*, just not implementable at scale.

**Fix:** split `_do_times` into `_combine_schema` (the cheap
schema/collision-check part, no tuple data) and the tuple-materializing
part. `times` (used standalone) still has to materialize the full
product, because that IS its result. But `Join` now streams pairs
directly -- one nested loop, evaluate the condition per pair, only add
matches to the output set -- so peak memory is proportional to the
*output* size, not `n*m`. Verified: n=16000 went from "not done after an
hour, 8+ GB RAM" to 190 seconds, and was faster per comparison too
(0.74μs vs. ~1.4μs before), because it's no longer paying set-insertion
and hashing costs for 256 million tuples that were about to be thrown
away anyway. Lesson: "times followed by select" is the right way to
*specify* what join means, but implementing it as two literal sequential
passes over a fully materialized intermediate relation is a trap the
spec's own wording invites -- worth being suspicious of any operator
defined "as A followed by B" when A can be enormous and B is a filter.

**Next:** re-run the full experiment with the fixed join, fill in
REPORT.md's table and the log-log analysis.
