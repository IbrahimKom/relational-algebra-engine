"""Evaluates a parsed AST bottom-up into a Relation. See README.md
"Qualification model" for the rule that decides how attribute names get
(re)qualified across rename/times/join -- it's summarized again next to
`_do_times` below since that's the one place it actually does work.
"""

from . import ast_nodes as ast
from .relation import Relation, Attr, value_type
from .errors import NameResolutionError, SchemaError, TypeCheckError

# instrumentation counters for the performance study (Section 8.2). Reset
# between runs by the caller (see perf/run_experiment.py).
COUNTERS = {"select_examined": 0, "join_compared": 0}


def build_environment(reldefs):
    env = {}
    for rd in reldefs:
        if rd.name in env:
            raise SchemaError(f"relation '{rd.name}' is defined more than once",
                               rd.line, rd.col)
        attrs = [Attr(None, a) for a in rd.attrs]
        tuples = {tuple(row) for row in rd.rows}
        env[rd.name] = Relation(rd.name, attrs, tuples)
    return env


def evaluate(node, env):
    if isinstance(node, ast.RelationRef):
        rel = env.get(node.name)
        if rel is None:
            raise NameResolutionError(f"unknown relation '{node.name}'",
                                       node.line, node.col)
        return rel

    if isinstance(node, ast.Select):
        rel = evaluate(node.child, env)
        # attribute names in `node.cond` resolve to the same column indices
        # for every row of this one Select -- the schema doesn't change
        # mid-loop -- so resolve each AttrRef once here instead of
        # re-searching rel.attrs by name on every single row.
        cache = {}
        kept = set()
        for row in rel.tuples:
            COUNTERS["select_examined"] += 1
            if _eval_cond(node.cond, row, rel, cache):
                kept.add(row)
        return Relation(rel.name, rel.attrs, kept)

    if isinstance(node, ast.Project):
        rel = evaluate(node.child, env)
        resolved = [_resolve_attr(rel, ar) for ar in node.attrs]
        seen = {}
        for ar, (idx, attr) in zip(node.attrs, resolved):
            if attr.qualified_name in seen:
                raise SchemaError(
                    f"attribute '{attr.qualified_name}' is projected more than "
                    f"once", ar.line, ar.col)
            seen[attr.qualified_name] = True
        indices = [i for i, _ in resolved]
        new_attrs = [a for _, a in resolved]
        new_tuples = {tuple(row[i] for i in indices) for row in rel.tuples}
        return Relation(rel.name, new_attrs, new_tuples)

    if isinstance(node, ast.Rename):
        rel = evaluate(node.child, env)
        return Relation(node.new_name, rel.attrs, rel.tuples)

    if isinstance(node, ast.BinSetOp):
        left = evaluate(node.left, env)
        right = evaluate(node.right, env)
        if node.op == "times":
            return _do_times(left, right, node)
        _check_union_compatible(left, right, node)
        if node.op == "union":
            result = left.tuples | right.tuples
        elif node.op == "intersect":
            result = left.tuples & right.tuples
        else:  # minus
            result = left.tuples - right.tuples
        return Relation(left.name, left.attrs, result)

    if isinstance(node, ast.Join):
        left = evaluate(node.left, env)
        right = evaluate(node.right, env)
        product = _do_times(left, right, node)
        # join[c] is times followed by select[c] (spec 4.3): every pair in
        # the product is compared against the condition exactly once. This
        # is computed directly (rather than incremented in a second loop
        # over product.tuples) so it isn't double-counted against the pair
        # count already implicit in how `product` was built.
        COUNTERS["join_compared"] += len(left.tuples) * len(right.tuples)
        cache = {}  # see the matching comment in the Select branch above
        kept = {row for row in product.tuples if _eval_cond(node.cond, row, product, cache)}
        return Relation(product.name, product.attrs, kept)

    raise AssertionError(f"unhandled AST node {node!r}")


# ---------------------------------------------------------------- times/join
#
# Qualification model (see also README.md): every Relation carries a
# `.name` -- its *current identity* -- separate from its column list. A
# base relation's identity is its definition name; `rename[X](...)` changes
# only the identity to X and leaves columns untouched. `times`/`join` is
# the one place identities turn into column qualifiers: each side's raw
# (unqualified) columns get prefixed with that side's *current* identity.
# A column that is already qualified (it came through an earlier
# times/join) is left alone -- it is not re-qualified a second time.
# This is what makes `rename[E2](Emp) join[...] Emp` (test case 20) work:
# the two sides have different identities ("E2" vs "Emp") at the moment of
# the join even though they both started from the same base relation.

def _do_times(left, right, node):
    def qualify(attrs, owner_name):
        return [Attr(a.qualifier if a.qualifier else owner_name, a.name) for a in attrs]

    combined = qualify(left.attrs, left.name) + qualify(right.attrs, right.name)
    seen = set()
    for a in combined:
        if a.qualified_name in seen:
            raise SchemaError(
                f"attribute '{a.qualified_name}' is ambiguous after combining "
                f"'{left.name}' and '{right.name}' -- use rename[...] on one "
                f"side to disambiguate", node.line, node.col)
        seen.add(a.qualified_name)

    tuples = {lrow + rrow for lrow in left.tuples for rrow in right.tuples}
    return Relation(left.name, combined, tuples)


# ------------------------------------------------------------- schema checks

def _check_union_compatible(left, right, node):
    opname = node.op
    if left.arity() != right.arity():
        raise SchemaError(
            f"'{opname}' requires relations with the same number of "
            f"attributes ({left.arity()} on the left, {right.arity()} on "
            f"the right)", node.line, node.col)
    for i, (a, b) in enumerate(zip(left.attrs, right.attrs), start=1):
        if a.qualified_name != b.qualified_name:
            raise SchemaError(
                f"'{opname}' requires the same attribute names in the same "
                f"order: position {i} is '{a.qualified_name}' on the left "
                f"but '{b.qualified_name}' on the right", node.line, node.col)
    lt, rt = left.col_types(), right.col_types()
    for i, (a, b) in enumerate(zip(lt, rt), start=1):
        if a is not None and b is not None and a != b:
            raise SchemaError(
                f"'{opname}': attribute '{left.attrs[i - 1].qualified_name}' "
                f"is {a} on the left but {b} on the right", node.line, node.col)


def _resolve_attr(rel, attr_ref):
    if attr_ref.qualifier is None:
        matches = [i for i, a in enumerate(rel.attrs) if a.name == attr_ref.name]
        if not matches:
            raise NameResolutionError(f"unknown attribute '{attr_ref.name}'",
                                       attr_ref.line, attr_ref.col)
        if len(matches) > 1:
            options = ", ".join(rel.attrs[i].qualified_name for i in matches)
            raise NameResolutionError(
                f"attribute '{attr_ref.name}' is ambiguous (matches {options}); "
                f"qualify it with a relation name", attr_ref.line, attr_ref.col)
        return matches[0], rel.attrs[matches[0]]

    exact = [i for i, a in enumerate(rel.attrs)
             if a.qualifier == attr_ref.qualifier and a.name == attr_ref.name]
    if exact:
        return exact[0], rel.attrs[exact[0]]
    if attr_ref.qualifier == rel.name:
        fallback = [i for i, a in enumerate(rel.attrs)
                    if a.qualifier is None and a.name == attr_ref.name]
        if fallback:
            return fallback[0], rel.attrs[fallback[0]]
    raise NameResolutionError(
        f"unknown attribute '{attr_ref.qualifier}.{attr_ref.name}'",
        attr_ref.line, attr_ref.col)


# --------------------------------------------------------------- conditions

def _eval_cond(cond, row, rel, cache):
    if isinstance(cond, ast.Or):
        return _eval_cond(cond.left, row, rel, cache) or _eval_cond(cond.right, row, rel, cache)
    if isinstance(cond, ast.And):
        return _eval_cond(cond.left, row, rel, cache) and _eval_cond(cond.right, row, rel, cache)
    if isinstance(cond, ast.Not):
        return not _eval_cond(cond.operand, row, rel, cache)
    if isinstance(cond, ast.Comparison):
        lv, lt = _eval_operand(cond.left, row, rel, cache)
        rv, rt = _eval_operand(cond.right, row, rel, cache)
        if lt != rt:
            raise TypeCheckError(
                f"cannot compare a {lt} to a {rt}", cond.line, cond.col)
        return _compare(cond.op, lv, rv)
    raise AssertionError(f"unhandled condition node {cond!r}")


def _eval_operand(node, row, rel, cache):
    if isinstance(node, ast.NumLit):
        return node.value, "number"
    if isinstance(node, ast.StrLit):
        return node.value, "string"
    if isinstance(node, ast.AttrRef):
        idx = cache.get(id(node))
        if idx is None:
            idx, _ = _resolve_attr(rel, node)
            cache[id(node)] = idx
        v = row[idx]
        return v, value_type(v)
    raise AssertionError(f"unhandled operand node {node!r}")


def _compare(op, lv, rv):
    if op == "=":
        return lv == rv
    if op == "!=":
        return lv != rv
    if op == "<":
        return lv < rv
    if op == "<=":
        return lv <= rv
    if op == ">":
        return lv > rv
    if op == ">=":
        return lv >= rv
    raise AssertionError(f"unhandled comparison operator {op!r}")
