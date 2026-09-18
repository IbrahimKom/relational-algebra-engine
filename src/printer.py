"""Parse tree printing (assignment Section 6.2) and result-table printing."""

from . import ast_nodes as ast


def _children(node):
    if isinstance(node, (ast.Select, ast.Project, ast.Rename)):
        return [node.child]
    if isinstance(node, ast.BinSetOp):
        return [node.left, node.right]
    if isinstance(node, ast.Join):
        return [node.left, node.right]
    if isinstance(node, ast.RelationRef):
        return []
    raise AssertionError(f"unhandled node in printer: {node!r}")


def format_tree(node):
    lines = [repr(node)]
    _render_children(node, "", lines)
    return "\n".join(lines)


def _render_children(node, prefix, lines):
    kids = _children(node)
    for idx, child in enumerate(kids):
        is_last = idx == len(kids) - 1
        branch = "└── " if is_last else "├── "
        lines.append(f"{prefix}{branch}{repr(child)}")
        child_prefix = prefix + ("    " if is_last else "│   ")
        _render_children(child, child_prefix, lines)


def format_relation(rel):
    """Print a relation as a schema header plus one row per line, sorted
    for reproducible output (tuple order is not otherwise meaningful --
    the relation is a set)."""
    header = ", ".join(a.qualified_name for a in rel.attrs)
    lines = [f"{rel.name}({header})"]
    for row in sorted(rel.tuples, key=lambda t: tuple(map(_sort_key, t))):
        lines.append("  " + ", ".join(_fmt_value(v) for v in row))
    if not rel.tuples:
        lines.append("  (empty -- 0 tuples)")
    return "\n".join(lines)


def _sort_key(v):
    # sort numbers before strings, deterministically, without crashing on
    # mixed-type columns
    return (0, v) if isinstance(v, (int, float)) else (1, v)


def _fmt_value(v):
    if isinstance(v, str):
        return f"'{v}'" if any(c in v for c in " ,()'") else v
    return str(v)
