"""Hand-written scanner. No regex anywhere (assignment rule).

One pass over the source, character by character. `peek`/`advance` are the
only primitives; every token method decides what it's looking at from the
current character (and, where maximal munch matters, one character of
lookahead) and consumes exactly the characters that belong to that token.
"""

from .tokens import Token, TokType
from .errors import LexError

_IDENT_START = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
_IDENT_CONT = _IDENT_START | set("0123456789")
_DIGITS = set("0123456789")


class Lexer:
    def __init__(self, source: str):
        self.src = source
        self.i = 0
        self.line = 1
        self.col = 1
        self.n = len(source)

    # ---- low level cursor ----

    def _peek(self, offset=0):
        j = self.i + offset
        return self.src[j] if j < self.n else ""

    def _advance(self):
        ch = self.src[self.i]
        self.i += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _make(self, type_, text, start_pos, start_line, start_col, value=None):
        return Token(type_, text, start_pos, start_line, start_col, value)

    # ---- public API ----

    def tokenize(self):
        """Return the full list of tokens, ending with one EOF token."""
        out = []
        while True:
            tok = self._next_token()
            out.append(tok)
            if tok.type == TokType.EOF:
                return out

    def _next_token(self):
        self._skip_whitespace_and_comments()
        if self.i >= self.n:
            return self._make(TokType.EOF, "", self.i, self.line, self.col)

        start_pos, start_line, start_col = self.i, self.line, self.col
        ch = self._peek()

        if ch == "\n":
            self._advance()
            return self._make(TokType.NEWLINE, "\n", start_pos, start_line, start_col)

        if ch in _IDENT_START:
            return self._scan_ident(start_pos, start_line, start_col)

        if ch in _DIGITS:
            return self._scan_number(start_pos, start_line, start_col)

        if ch == "-":
            if self._peek(1) in _DIGITS:
                return self._scan_number(start_pos, start_line, start_col)
            raise LexError(
                f"unexpected character '-' (not followed by a digit, "
                f"and this language has no subtraction operator)",
                start_line, start_col)

        if ch == "'":
            return self._scan_string(start_pos, start_line, start_col)

        # single/double-char punctuation, maximal munch on the comparisons
        two = ch + self._peek(1)
        if two in (">=", "<=", "!="):
            self._advance()
            self._advance()
            kind = {">=": TokType.GTE, "<=": TokType.LTE, "!=": TokType.NEQ}[two]
            return self._make(kind, two, start_pos, start_line, start_col)

        single_map = {
            "(": TokType.LPAREN, ")": TokType.RPAREN,
            "[": TokType.LBRACKET, "]": TokType.RBRACKET,
            "{": TokType.LBRACE, "}": TokType.RBRACE,
            ",": TokType.COMMA, ".": TokType.DOT,
            "=": TokType.ASSIGN, "<": TokType.LT, ">": TokType.GT,
        }
        if ch in single_map:
            self._advance()
            return self._make(single_map[ch], ch, start_pos, start_line, start_col)

        if ch == "!":
            # '!' alone is never valid -- only '!=' is a token in this language
            raise LexError(f"unexpected character '!' (did you mean '!='?)",
                            start_line, start_col)

        raise LexError(f"unexpected character {ch!r}", start_line, start_col)

    # ---- whitespace / comments ----

    def _skip_whitespace_and_comments(self):
        while self.i < self.n:
            ch = self._peek()
            if ch in (" ", "\t", "\r"):
                self._advance()
            elif ch == "/" and self._peek(1) == "/":
                while self.i < self.n and self._peek() != "\n":
                    self._advance()
                # the trailing '\n' itself is left for _next_token to emit
                # as a NEWLINE, so a comment line still separates tuples
            else:
                return

    # ---- token scanners ----

    def _scan_ident(self, start_pos, start_line, start_col):
        j = self.i
        while self.i < self.n and self._peek() in _IDENT_CONT:
            self._advance()
        text = self.src[j:self.i]
        return self._make(TokType.IDENT, text, start_pos, start_line, start_col)

    def _scan_number(self, start_pos, start_line, start_col):
        j = self.i
        if self._peek() == "-":
            self._advance()
        while self.i < self.n and self._peek() in _DIGITS:
            self._advance()
        if self._peek() == "." and self._peek(1) in _DIGITS:
            self._advance()  # consume '.'
            while self.i < self.n and self._peek() in _DIGITS:
                self._advance()
        text = self.src[j:self.i]
        value = float(text) if "." in text else int(text)
        return self._make(TokType.NUMBER, text, start_pos, start_line, start_col, value)

    def _scan_string(self, start_pos, start_line, start_col):
        self._advance()  # opening quote
        chars = []
        while True:
            if self.i >= self.n:
                raise LexError("unterminated string literal (missing closing \"'\")",
                                start_line, start_col)
            ch = self._peek()
            if ch == "'":
                if self._peek(1) == "'":
                    chars.append("'")
                    self._advance()
                    self._advance()
                    continue
                self._advance()  # closing quote
                break
            if ch == "\n":
                raise LexError("unterminated string literal (hit end of line)",
                                start_line, start_col)
            chars.append(ch)
            self._advance()
        value = "".join(chars)
        text = self.src[start_pos:self.i]
        return self._make(TokType.STRING, text, start_pos, start_line, start_col, value)
