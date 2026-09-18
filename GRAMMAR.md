# GRAMMAR.md — Relational Algebra Engine Language Design

## 0. Status

Draft written **before** the parser exists, as the assignment requires.
This should be revisited once the tokenizer/parser are implemented: if
anything here turns out to be unimplementable as written, or the parser
needs a rule this draft didn't anticipate, fix it here and note the change
(with a reason) in [DESIGN_LOG.md](DESIGN_LOG.md) rather than silently
editing history.

---

## 1. The grammar (EBNF)

Notation: `::=` defines a rule, `|` is alternation, `[ ]` is optional,
`{ }` is zero-or-more repetition, `" "` is a literal token, `UPPERCASE`
names are terminals produced by the tokenizer (Section 6), everything else
is a nonterminal.

```ebnf
(* ===================== Top level ===================== *)

Program        ::= { RelationDef } [ Query ] EOF

(* ===================== Relation definitions ===================== *)

RelationDef    ::= IDENT "(" AttrList ")" "=" "{" TupleBlock "}"

AttrList       ::= IDENT { "," IDENT }

TupleBlock     ::= { NEWLINE } { TupleLine { NEWLINE } }

TupleLine      ::= Value { "," Value }

Value          ::= NUMBER
                  | STRING
                  | BAREWORD                (* unquoted string value, see 6.4 *)

(* ===================== Queries : relational expressions =====================
   Precedence, low to high (see Section 2 for the full table):
     1 (lowest)   union, minus     (left-assoc)
     2            intersect        (left-assoc)
     3            times, join      (left-assoc)
     4 (highest)  select/project/rename, parens, relation names
*)

Query          ::= Expr

Expr           ::= SetLevel

SetLevel       ::= IntersectLevel { ("union" | "minus") IntersectLevel }

IntersectLevel ::= ProductLevel { "intersect" ProductLevel }

ProductLevel   ::= Primary { ("times" | "join" "[" Condition "]") Primary }

Primary        ::= "select" "[" Condition "]" "(" Expr ")"
                  | "project" "[" AttrRefList "]" "(" Expr ")"
                  | "rename" "[" IDENT "]" "(" Expr ")"
                  | "(" Expr ")"
                  | IDENT

AttrRefList    ::= AttrRef { "," AttrRef }

AttrRef        ::= [ IDENT "." ] IDENT

(* ===================== Conditions =====================
   Precedence, low to high:
     1 (lowest)   or     (left-assoc)
     2            and    (left-assoc)
     3            not    (right-assoc, unary prefix)
     4 (highest)  comparison, parens
*)

Condition      ::= OrCond

OrCond         ::= AndCond { "or" AndCond }

AndCond        ::= NotCond { "and" NotCond }

NotCond        ::= "not" NotCond
                  | CondPrimary

CondPrimary    ::= "(" Condition ")"
                  | Comparison

Comparison     ::= Operand CompOp Operand

CompOp         ::= "=" | "!=" | "<=" | ">=" | "<" | ">"

Operand        ::= NUMBER | STRING | AttrRef
```

Each rule is named after the operator(s) it parses, and calls the next
tier up for its operands: `SetLevel` (union/minus) is built from
`IntersectLevel` operands, `IntersectLevel` is built from `ProductLevel`
operands, and `ProductLevel` (times/join) is built from `Primary`
operands.

---

## 2. Precedence and associativity

### 2.1 Relational (set/product) operators

| Level | Operators | Associativity | Grammar rule |
|---|---|---|---|
| 1 (lowest) | `union`, `minus` | left | `SetLevel` |
| 2 | `intersect` | left | `ProductLevel` |
| 3 (highest) | `times`, `join[...]` | left | `IntersectLevel` |

**Rationale.** This mirrors ordinary arithmetic precedence (`+`/`-` below
`*`), and the analogy is not just mnemonic — it is semantically load-bearing:

- `union`/`minus` behave like `+`/`-`: `minus` is **not** commutative and
  **not** associative (exactly like subtraction), so it must sit in a tier
  where grouping is resolved strictly left-to-right, the same way
  `A - B - C` means `(A - B) - C` and not `A - (B - C)`.
- `intersect` behaves like `*`: it **distributes** over `union`,
  `A intersect (B union C) = (A intersect B) union (A intersect C)`,
  exactly like `a * (b + c) = a*b + a*c`. Giving it higher precedence than
  `union`/`minus` means `A union B intersect C` reads as
  `A union (B intersect C)`, matching how nobody reads `a + b * c` as
  `(a + b) * c`.
- `times`/`join` bind tightest because they are the most "primary" way to
  combine two relations (a join is literally a filtered product), the
  same way multiplication binds tighter than addition because it is a
  more fundamental combination of two numbers.

`select`, `project`, `rename` are not part of this table because they are
**unary prefix operators with a mandatory parenthesized argument**
(`select[cond](Expr)`) — the parentheses make their scope explicit in the
concrete syntax itself, so there is no precedence question to resolve for
them. They sit at `Primary`, the same tier as a bare relation name or an
explicitly-parenthesized `Expr`.

### 2.2 Boolean condition operators

| Level | Operator | Associativity | Grammar rule |
|---|---|---|---|
| 1 (lowest) | `or` | left | `OrCond` |
| 2 | `and` | left | `AndCond` |
| 3 (highest) | `not` | right (unary prefix) | `NotCond` |

This is the standard precedence used by every mainstream language with
boolean operators (Python, C, Java): `not` binds to the single condition
immediately after it, `and` groups tighter than `or` the same way `*`
groups tighter than `+`. Comparisons (`=`, `!=`, `<`, `<=`, `>`, `>=`) are
all at the same, highest precedence and are **non-associative** — the
grammar (`Comparison ::= Operand CompOp Operand`) makes `a = b = c`
a syntax error rather than silently picking a grouping, since chained
comparisons are not part of the specified language.

### 2.3 Contextual (soft) keywords

`union`, `minus`, `intersect`, `times`, `join`, `select`, `project`,
`rename`, `and`, `or`, `not` are **not** reserved words in the tokenizer.
The tokenizer only ever emits a generic `IDENT` token for any
letter-starting word; it does not know these spellings are special.

The **parser** decides whether a given `IDENT` token is being used as an
operator keyword, and it only does so by checking the token's *text* at
the specific points in the grammar above where an operator keyword is
syntactically expected next — e.g. inside the `{ ("union"|"minus") ... }`
loop of `SetLevel`, after a `Primary` has already been parsed. Everywhere
else — in particular, as an `Operand` inside a `Comparison`, or as the
`IDENT` naming a bare relation reference in `Primary` — any spelling,
keyword-shaped or not, is simply an identifier.

This resolves test case 8 (`select[union=3](R)`) cleanly: inside
`Comparison`, the grammar only ever expects an `Operand`, never an
operator keyword, so `union` here is unconditionally an attribute name.
It also means a relation could legally be named `Union` (case differs, but
even `union` verbatim would parse as a relation reference in `Primary`
position, since `Primary`'s only use of a bare word is `IDENT` — a keyword
check never runs there).

---

## 3. Ambiguity demonstration

### 3.1 The naive grammar

```ebnf
Expr ::= Expr "union" Expr
       | Expr "minus" Expr
       | "(" Expr ")"
       | IDENT
```

### 3.2 Two parse trees for `A union B minus C`

```
Tree 1 (union binds first, "minus" is the root):

        minus
       /     \
    union      C
    /   \
   A     B

Tree 2 (minus binds first, "union" is the root):

        union
       /     \
      A     minus
            /   \
           B     C
```

Both are valid parses of the naive grammar: it gives no rule for which
`Expr "op" Expr` alternative "wins" when both a left `union` and a right
`minus` are available, so a parser (or a human) can legally bracket the
input either way.

### 3.3 A concrete instance where the two trees disagree

Let all three relations have a single attribute `X`:

```
A(X) = { 1 }
B(X) = { 1 }
C(X) = { 1 }
```

**Tree 1** — `(A union B) minus C`:
`A union B = {1}`, then `{1} minus {1} = {}` → **result: `{}`**

**Tree 2** — `A union (B minus C)`:
`B minus C = {1} minus {1} = {}`, then `A union {} = {1}` → **result: `{1}`**

`{}` ≠ `{1}`: the two trees produce genuinely different query results from
identical input, which is exactly what "ambiguous" has to mean for a query
language — the same text can silently mean two different things depending
on which tree the parser happens to build.

### 3.4 The stratified grammar that removes the ambiguity

```ebnf
SetLevel     ::= ProductLevel { ("union" | "minus") ProductLevel }
ProductLevel ::= IDENT | "(" Expr ")"      (* simplified for this demo *)
```

`SetLevel` is no longer recursive on the left in the dangerous sense: it
parses one `ProductLevel` operand, then **iterates**, left to right,
consuming `("union"|"minus") ProductLevel` pairs and folding each new
operand onto an accumulator as it goes (see Section 4 for why this shape
was chosen over direct left recursion). Because the fold is strictly
left-to-right, `A union B minus C` is forced into
**`(A union B) minus C` — Tree 1** — the only tree consistent with the
associativity documented in Section 2.1 (`union`/`minus` are same-tier,
left-associative, exactly like `+`/`-`).

---

## 4. Parsing strategy justification

**Strategy: recursive descent**, one function per nonterminal, single-token
lookahead (`peek()`), no backtracking anywhere in the grammar above.

**Why recursive descent.** Every rule in Section 1 can be resolved with one
token of lookahead: at any point in parsing, the next token's kind (and,
for `IDENT`s in operator position, its text) uniquely determines which
alternative to take. That is precisely the condition under which
recursive descent works without backtracking or a parser-generator table
— so a hand-written `parse_X()` function per nonterminal is both sufficient
and the most direct way to satisfy the "no parser generators" rule while
keeping error messages (Section 6.3) attached to a specific point in a
specific function, which a generated table-driven parser makes much
harder to do well.

**What left recursion would do to it, and where it was removed.** A
recursive-descent function for a left-recursive rule such as the naive

```ebnf
Expr ::= Expr "union" Expr | ...
```

would begin by calling itself, `parse_expr()` immediately calling
`parse_expr()`, before consuming any token — an infinite call chain that
overflows the stack without ever reading input. Every binary-operator tier
in Section 1 (`SetLevel`, `ProductLevel`, `IntersectLevel`, `OrCond`,
`AndCond`) is written instead in the **iterative "operand, then loop"**
shape:

```ebnf
SetLevel ::= IntersectLevel { ("union" | "minus") IntersectLevel }
```

which is not left-recursive — it starts by unconditionally parsing one
operand, consuming real input before any decision is made — and translates
directly into a `while` loop in the corresponding parser function:

```python
def parse_set_level():
    left = parse_intersect_level()
    while peek().text in ("union", "minus"):
        op = advance().text
        right = parse_intersect_level()
        left = BinOp(op, left, right)
    return left
```

This loop both avoids left recursion *and* gives left-associativity for
free, since each new right-hand operand is folded onto the existing `left`
node rather than the other way around — the same trick used to remove left
recursion from arithmetic-expression grammars in general (Dragon Book
§4.3, Crafting Interpreters ch. 6). `NotCond`'s `"not" NotCond` is real
recursion, not left recursion (the recursive call is *after* consuming the
`not` token), so it is written as ordinary right-recursion and needs no
such rewrite.

---

## 5. Sources

- *Crafting Interpreters*, Robert Nystrom — scanning (ch. 4) and parsing
  expressions (ch. 6, esp. the precedence-climbing / recursive-descent
  translation of a precedence table into nested grammar rules). Free at
  https://craftinginterpreters.com/.
- Wikipedia: *Extended Backus–Naur form*, *Recursive descent parser*,
  *Maximal munch*, *Operator-precedence parser* — used to check the EBNF
  notation in Section 1 and to confirm the standard definition of maximal
  munch used in Section 6.2.
- Aho, Lam, Sethi, Ullman, *Compilers: Principles, Techniques, and Tools*
  (Dragon Book), §§2.2–2.4 (syntax-directed translation basics) and §4.4
  (top-down parsing, left-recursion elimination) — formal treatment behind
  the left-recursion rewrite in Section 4.
- AI assistance (Claude) was used throughout for drafting and for
  generating first-pass code from the finished grammar. Where it produced
  something wrong, slow, or incomplete, that is logged with the specific
  symptom and fix in [DESIGN_LOG.md](DESIGN_LOG.md) rather than here — this
  section only records general reading, per the assignment's split between
  "what you read" (here) and the AI-failure log (DESIGN_LOG.md).
