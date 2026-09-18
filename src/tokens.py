"""Token types and the Token record produced by the hand-written lexer."""

from enum import Enum, auto


class TokType(Enum):
    IDENT = auto()      # word: relation/attribute name, keyword spelling, or
                         # (only when the parser is reading a tuple Value) a
                         # bare unquoted string -- the lexer does not
                         # distinguish these; the parser does, by context.
    NUMBER = auto()      # 123, -30, 3.5
    STRING = auto()      # quoted 'like this', with '' as an escaped quote

    # punctuation
    LPAREN = auto()       # (
    RPAREN = auto()       # )
    LBRACKET = auto()     # [
    RBRACKET = auto()     # ]
    LBRACE = auto()       # {
    RBRACE = auto()       # }
    COMMA = auto()        # ,
    DOT = auto()          # .
    ASSIGN = auto()       # =  (relation definition '=', reused as comparison '=')

    # comparison operators
    NEQ = auto()          # !=
    LT = auto()           # <
    LTE = auto()          # <=
    GT = auto()           # >
    GTE = auto()          # >=

    NEWLINE = auto()      # significant only inside a relation's tuple block
    EOF = auto()


class Token:
    __slots__ = ("type", "text", "value", "pos", "line", "col")

    def __init__(self, type_, text, pos, line, col, value=None):
        self.type = type_
        self.text = text
        self.value = value
        self.pos = pos      # 0-based character offset into the source
        self.line = line    # 1-based
        self.col = col      # 1-based

    def __repr__(self):
        return f"Token({self.type.name}, {self.text!r}, {self.line}:{self.col})"


# Words that are only treated as operators when the parser is at a grammar
# position expecting one (see GRAMMAR.md Section 2.3). The lexer does not
# use this set at all -- it always emits IDENT for word tokens.
RELATIONAL_KEYWORDS = {"select", "project", "rename",
                        "union", "intersect", "minus", "times", "join"}
CONDITION_KEYWORDS = {"and", "or", "not"}
