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

**Result:** full 1000→64000 run completed in ~81 minutes (down from an
estimated ~2 hours with the old implementation, and it would have needed
tens of GB of RAM to even finish at 32000/64000 rather than just being
slow). Comparisons matched `n*m` exactly at every size, log-log slope of
wall time vs n came out to ≈2.095 (predicted: ≈2, for an `O(n^2)`
algorithm) -- both filled into REPORT.md along with the select/project
comparison and the 1,000,000-tuple extrapolation (≈10.5 days, showing why
that size isn't run). Match-rate sub-study rerun in isolation on the fixed
implementation for a clean number: match rate changes neither comparison
count nor wall time, as expected for a nested-loop join with no index.

**Project status:** engine, grammar doc, error handling, tests, and
performance study are all done and pushed. What's left is entirely on me:
re-read `src/lexer.py`/`parser.py`/`interpreter.py` cold until I can
explain every line without notes (see ORAL_PREP.md), then record the
5-minute video.

---

## 2026-09-29 — Cross-checked against the course forum Q&A

**Goal:** go through the professor's forum answers to other students'
questions and make sure the implementation actually matches what's being
asked for, since the assignment PDF alone left some things ambiguous.

**What I checked against six forum Q&As:**
- Tokenizer/one-AST/panic-mode error handling (Amiras's Q1) -- already
  matched exactly: `>=` is one token, `--tree` and execution share the
  same AST, parser raises on the first syntax error with no recovery.
- `rename` is in-memory only (Q5) -- already true; `Rename` evaluation
  never touches `env`.
- Type errors apply to `=`/`!=`, not just ordering operators (Logan's Q6)
  -- already true (the type check in `_eval_cond` runs before the
  operator is even looked at), but added two regression tests
  (`test_type_error_applies_to_equality_not_just_ordering`,
  `test_same_type_comparisons_all_work`) to `tests/test_extra.py` so it's
  explicitly locked in and citable.
- Match rate should be varied and its impact reported (Q2) -- already
  covered by the Section 8.4 Q5 sub-study from the previous session.

**AI assistance issue #5:** Section 8.2 originally read "increment once
for every pair of tuples your join compares, and once for every tuple
your selection examines" -- ambiguous enough that another student asked
about it, and the professor rewrote it. The rewrite requires "a counter
inside your join implementation, incremented once for every pair of
tuples the join condition is evaluated on" -- i.e. a literal per-pair
`+= 1` sitting inside the nested loop. Claude's implementation computed
the exact same number as `len(left.tuples) * len(right.tuples)` up front
instead, which is mathematically identical (nothing in the loop ever
skips a pair) but isn't what the rewritten instruction literally asks
for, and is a worse answer to "where in your code does the counting
happen" during the oral check. Fixed: moved the increment to a plain
local variable bumped once per iteration inside the loop, flushed to
`COUNTERS` after the loop (a bare `COUNTERS[...] += 1` per pair added a
genuine ~60% wall-time regression at n=4000 from repeated dict lookups
across billions of iterations -- confirmed by timing both versions back
to back -- so the local-variable version keeps the literal per-pair
semantics without that cost). Lesson: when a course clarification changes
*how* something must be computed, check whether the "obviously correct
and slightly faster" version Claude already wrote is still an acceptable
implementation of the newly-precise wording, even when the output value
doesn't change.

**Result:** reran the full 1000-64000 table after closing Discord/Spotify/
etc. (~84 minutes). Comparisons still exactly `n*m` at every size, as
expected. Wall times came out slightly *slower* than the previous run
(e.g. n=64000: 4015s vs. the old 3701s) despite the quieter machine --
that's the real, expected cost of the per-pair counter increment now
sitting inside the hot loop, not noise. Log-log slope moved from ≈2.095
to ≈2.112, still solidly consistent with O(n²). REPORT.md updated with
final numbers and the plot regenerated.

---

## 2026-09-30 — Reading my own code before the video/oral check, found dead code

**Goal:** actually read through `src/` myself, file by file, instead of just
having it explained to me, before recording the required video.

**What I did:** went through `tokens.py`, `lexer.py`, `parser.py`, and
`interpreter.py` line by line. Asked about a couple of Python syntax
things I didn't recognize (`Enum`/`auto()`, `__slots__`) and got those
cleared up.

**AI assistance issue #6:** while reading `tokens.py` I asked what
`RELATIONAL_KEYWORDS` and `CONDITION_KEYWORDS` were for. Checked with a
grep across `src/` -- they were imported into `parser.py` but never
actually referenced anywhere; every real keyword check in the parser
(`check_kw("union", "minus")`, `check_kw("or")`, etc.) uses its own
hardcoded literal strings per precedence tier instead, because each tier
needs a different subset of keywords, not the whole blob. Claude had left
these two sets in from an earlier draft of the soft-keyword design and
never cleaned them up once the parser settled on per-tier literals. Fixed
by deleting both unused sets and the now-unused import, and moving the
design-rationale comment that used to sit above them to `check_kw` itself
in parser.py, where it actually describes real, currently-running code.
Lesson: dead code doesn't just sit there harmlessly -- it's an easy way to
get caught flat-footed in an oral check if someone points at it and asks
"what's this for" and the honest answer turns out to be "nothing." Reading
my own code start to finish, not just the parts I was walked through, is
what caught this.
