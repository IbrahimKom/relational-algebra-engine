"""In-memory relation representation.

A relation is a *set* of tuples (Python tuples of int/float/str) plus an
ordered schema of Attr(qualifier, name) pairs, plus a `name` -- the current
identity of the relation, used to auto-qualify its columns the next time it
is combined with another relation via times/join (see design note in
README.md "Qualification model").
"""


class Attr:
    __slots__ = ("qualifier", "name")

    def __init__(self, qualifier, name):
        self.qualifier = qualifier
        self.name = name

    @property
    def qualified_name(self):
        return f"{self.qualifier}.{self.name}" if self.qualifier else self.name

    def __eq__(self, other):
        return (isinstance(other, Attr) and self.qualifier == other.qualifier
                and self.name == other.name)

    def __hash__(self):
        return hash((self.qualifier, self.name))

    def __repr__(self):
        return self.qualified_name


def value_type(v):
    return "number" if isinstance(v, (int, float)) else "string"


class Relation:
    def __init__(self, name, attrs, tuples):
        self.name = name              # current identity, for future qualification
        self.attrs = attrs            # list[Attr], the ordered schema
        self.tuples = set(tuples)     # set[tuple[value, ...]]

    def arity(self):
        return len(self.attrs)

    def col_types(self):
        """One inferred type ('number'/'string'/None) per column, sampled
        from an arbitrary tuple (columns are assumed type-homogeneous --
        see README.md). None (unknown) if the relation is empty."""
        if not self.tuples:
            return [None] * self.arity()
        sample = next(iter(self.tuples))
        return [value_type(v) for v in sample]

    def __repr__(self):
        return f"Relation({self.name}, attrs={self.attrs}, |tuples|={len(self.tuples)})"
