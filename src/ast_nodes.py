"""AST node types. Plain data classes -- no behaviour here; evaluation lives
in interpreter.py so the tree can be printed (Section 6.2) without running it.
"""


class Node:
    """Base class only so isinstance checks and printer.py have one root."""
    pass


# ---------------------------------------------------------------- relational

class RelationRef(Node):
    def __init__(self, name, line, col):
        self.name = name
        self.line, self.col = line, col

    def __repr__(self):
        return f"Relation({self.name})"


class Select(Node):
    def __init__(self, cond, child, line, col):
        self.cond, self.child = cond, child
        self.line, self.col = line, col

    def __repr__(self):
        return f"Select(cond={self.cond})"


class Project(Node):
    def __init__(self, attrs, child, line, col):
        self.attrs, self.child = attrs, child  # attrs: list[AttrRef]
        self.line, self.col = line, col

    def __repr__(self):
        return f"Project(attrs=[{', '.join(str(a) for a in self.attrs)}])"


class Rename(Node):
    def __init__(self, new_name, child, line, col):
        self.new_name, self.child = new_name, child
        self.line, self.col = line, col

    def __repr__(self):
        return f"Rename(to={self.new_name})"


class BinSetOp(Node):
    """union / intersect / minus / times -- op is one of those four strings."""

    def __init__(self, op, left, right, line, col):
        self.op, self.left, self.right = op, left, right
        self.line, self.col = line, col

    def __repr__(self):
        return f"{self.op.capitalize()}"


class Join(Node):
    def __init__(self, cond, left, right, line, col):
        self.cond, self.left, self.right = cond, left, right
        self.line, self.col = line, col

    def __repr__(self):
        return f"Join(cond={self.cond})"


# ----------------------------------------------------------------- condition

class Or(Node):
    def __init__(self, left, right):
        self.left, self.right = left, right

    def __repr__(self):
        return f"Or({self.left!r}, {self.right!r})"


class And(Node):
    def __init__(self, left, right):
        self.left, self.right = left, right

    def __repr__(self):
        return f"And({self.left!r}, {self.right!r})"


class Not(Node):
    def __init__(self, operand):
        self.operand = operand

    def __repr__(self):
        return f"Not({self.operand!r})"


class Comparison(Node):
    def __init__(self, op, left, right, line, col):
        self.op, self.left, self.right = op, left, right
        self.line, self.col = line, col

    def __repr__(self):
        op_name = {"=": "Eq", "!=": "Ne", "<": "Lt", "<=": "Le",
                   ">": "Gt", ">=": "Ge"}[self.op]
        return f"{op_name}({self.left!r}, {self.right!r})"


# ------------------------------------------------------------------ operands

class NumLit(Node):
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return f"Num({self.value})"


class StrLit(Node):
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return f"Str({self.value!r})"


class AttrRef(Node):
    def __init__(self, qualifier, name, line, col):
        self.qualifier, self.name = qualifier, name
        self.line, self.col = line, col

    def __str__(self):
        return f"{self.qualifier}.{self.name}" if self.qualifier else self.name

    def __repr__(self):
        return f"Attr({self})"
