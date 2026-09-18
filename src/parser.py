"""Hand-written recursive descent parser. See GRAMMAR.md for the EBNF this
follows rule-for-rule -- every parse_X method below corresponds to exactly
one nonterminal there.

Two entry points:
  parse_program(tokens) -> (relation_defs, query_or_None)
      the full `{RelationDef} [Query] EOF` form, used for a database file
  parse_query(tokens)   -> query AST (or None for an empty/whitespace input)
      just a bare query expression, used e.g. by `--tree "..."`
"""

from .tokens import TokType, RELATIONAL_KEYWORDS, CONDITION_KEYWORDS
from .errors import ParseError
from . import ast_nodes as ast


class RelationDefResult:
    __slots__ = ("name", "attrs", "rows", "line", "col")

    def __init__(self, name, attrs, rows, line, col):
        self.name, self.attrs, self.rows = name, attrs, rows
        self.line, self.col = line, col


class Parser:
    def __init__(self, tokens):
        self.toks = tokens
        self.i = 0

    # ---------------------------------------------------------- raw cursor

    def _raw(self, offset=0):
        j = self.i + offset
        return self.toks[j] if j < len(self.toks) else self.toks[-1]

    def _skip_newlines(self):
        while self.toks[self.i].type == TokType.NEWLINE:
            self.i += 1

    def cur(self):
        """Current token, skipping over NEWLINEs (they are not significant
        outside a relation's tuple block)."""
        self._skip_newlines()
        return self.toks[self.i]

    def advance(self):
        tok = self.cur()
        self.i += 1
        return tok

    def check(self, type_):
        return self.cur().type == type_

    def check_kw(self, *words):
        t = self.cur()
        return t.type == TokType.IDENT and t.text in words

    def expect(self, type_, what):
        tok = self.cur()
        if tok.type != type_:
            raise ParseError(f"expected {what}, found {_describe(tok)}",
                              tok.line, tok.col)
        return self.advance()

    def expect_kw(self, word):
        tok = self.cur()
        if not (tok.type == TokType.IDENT and tok.text == word):
            raise ParseError(f"expected '{word}', found {_describe(tok)}",
                              tok.line, tok.col)
        return self.advance()

    # -------------------------------------------------------------- program

    def parse_program(self):
        defs = []
        while self.check(TokType.IDENT) and self._raw_after_ident_is_lparen():
            defs.append(self._parse_relation_def())
        self._skip_newlines()
        query = None
        if not self.check(TokType.EOF):
            query = self.parse_expr()
        self._skip_newlines()
        self.expect(TokType.EOF, "end of input")
        return defs, query

    def _raw_after_ident_is_lparen(self):
        # lookahead past the current IDENT (without consuming) to see if a
        # relation-definition is starting: IDENT "(" ... ")" "=" "{"
        j = self.i
        while self.toks[j].type == TokType.NEWLINE:
            j += 1
        j += 1  # past the IDENT itself
        while self.toks[j].type == TokType.NEWLINE:
            j += 1
        return self.toks[j].type == TokType.LPAREN

    # ------------------------------------------------------ relation defs

    def _parse_relation_def(self):
        name_tok = self.expect(TokType.IDENT, "relation name")
        self.expect(TokType.LPAREN, "'(' after relation name")
        attrs = [self.expect(TokType.IDENT, "attribute name").text]
        while self.check(TokType.COMMA):
            self.advance()
            attrs.append(self.expect(TokType.IDENT, "attribute name").text)
        self.expect(TokType.RPAREN, "')' to close attribute list")
        self.expect(TokType.ASSIGN, "'=' after attribute list")
        self.expect(TokType.LBRACE, "'{' to start tuple block")
        rows = self._parse_tuple_block(name_tok.text, len(attrs))
        self.expect(TokType.RBRACE, "'}' to close tuple block")
        return RelationDefResult(name_tok.text, attrs, rows,
                                  name_tok.line, name_tok.col)

    def _parse_tuple_block(self, rel_name, arity):
        # NEWLINE is significant here: it separates tuple lines. This
        # method intentionally does NOT use cur()/advance(), since those
        # silently skip newlines -- here we need to see them.
        rows = []
        while self.toks[self.i].type == TokType.NEWLINE:
            self.i += 1
        while self.toks[self.i].type != TokType.RBRACE:
            row = [self._parse_value()]
            while self.toks[self.i].type == TokType.COMMA:
                self.i += 1
                row.append(self._parse_value())
            if len(row) != arity:
                tok = self.toks[self.i]
                raise ParseError(
                    f"relation '{rel_name}' has {arity} attributes but this "
                    f"tuple has {len(row)} values", tok.line, tok.col)
            rows.append(row)
            tok = self.toks[self.i]
            if tok.type == TokType.NEWLINE:
                while self.toks[self.i].type == TokType.NEWLINE:
                    self.i += 1
            elif tok.type == TokType.RBRACE:
                break
            else:
                raise ParseError(
                    f"expected end of line after tuple, found {_describe(tok)}",
                    tok.line, tok.col)
        return rows

    def _parse_value(self):
        tok = self.toks[self.i]
        if tok.type == TokType.NUMBER:
            self.i += 1
            return tok.value
        if tok.type == TokType.STRING:
            self.i += 1
            return tok.value
        if tok.type == TokType.IDENT:
            self.i += 1
            return tok.text  # bare (unquoted) string value
        raise ParseError(f"expected a value (number or string), found {_describe(tok)}",
                          tok.line, tok.col)

    # ---------------------------------------------------- relational exprs

    def parse_expr(self):
        return self._parse_set_level()

    def _parse_set_level(self):
        left = self._parse_intersect_level()
        while self.check_kw("union", "minus"):
            op_tok = self.advance()
            right = self._parse_intersect_level()
            left = ast.BinSetOp(op_tok.text, left, right, op_tok.line, op_tok.col)
        return left

    def _parse_intersect_level(self):
        left = self._parse_product_level()
        while self.check_kw("intersect"):
            op_tok = self.advance()
            right = self._parse_product_level()
            left = ast.BinSetOp("intersect", left, right, op_tok.line, op_tok.col)
        return left

    def _parse_product_level(self):
        left = self._parse_primary()
        while self.check_kw("times", "join"):
            op_tok = self.advance()
            if op_tok.text == "times":
                right = self._parse_primary()
                left = ast.BinSetOp("times", left, right, op_tok.line, op_tok.col)
            else:
                self.expect(TokType.LBRACKET, "'[' after 'join'")
                cond = self.parse_condition()
                self.expect(TokType.RBRACKET, "']' to close join condition")
                right = self._parse_primary()
                left = ast.Join(cond, left, right, op_tok.line, op_tok.col)
        return left

    def _parse_primary(self):
        tok = self.cur()

        if tok.type == TokType.IDENT and tok.text == "select":
            self.advance()
            self.expect(TokType.LBRACKET, "'[' after 'select'")
            cond = self.parse_condition()
            self.expect(TokType.RBRACKET, "']' to close select condition")
            self.expect(TokType.LPAREN, "'(' after select[...]")
            child = self.parse_expr()
            self.expect(TokType.RPAREN, "')' to close select(...)")
            return ast.Select(cond, child, tok.line, tok.col)

        if tok.type == TokType.IDENT and tok.text == "project":
            self.advance()
            self.expect(TokType.LBRACKET, "'[' after 'project'")
            attrs = self._parse_attr_ref_list()
            self.expect(TokType.RBRACKET, "']' to close project attribute list")
            self.expect(TokType.LPAREN, "'(' after project[...]")
            child = self.parse_expr()
            self.expect(TokType.RPAREN, "')' to close project(...)")
            return ast.Project(attrs, child, tok.line, tok.col)

        if tok.type == TokType.IDENT and tok.text == "rename":
            self.advance()
            self.expect(TokType.LBRACKET, "'[' after 'rename'")
            new_name = self.expect(TokType.IDENT, "new relation name").text
            self.expect(TokType.RBRACKET, "']' to close rename[...]")
            self.expect(TokType.LPAREN, "'(' after rename[...]")
            child = self.parse_expr()
            self.expect(TokType.RPAREN, "')' to close rename(...)")
            return ast.Rename(new_name, child, tok.line, tok.col)

        if tok.type == TokType.LPAREN:
            self.advance()
            inner = self.parse_expr()
            self.expect(TokType.RPAREN, "')' to close parenthesized expression")
            return inner

        if tok.type == TokType.IDENT:
            self.advance()
            return ast.RelationRef(tok.text, tok.line, tok.col)

        raise ParseError(f"expected a relation expression, found {_describe(tok)}",
                          tok.line, tok.col)

    def _parse_attr_ref_list(self):
        attrs = [self._parse_attr_ref()]
        while self.check(TokType.COMMA):
            self.advance()
            attrs.append(self._parse_attr_ref())
        return attrs

    def _parse_attr_ref(self):
        first = self.expect(TokType.IDENT, "attribute name")
        if self.check(TokType.DOT):
            self.advance()
            second = self.expect(TokType.IDENT, "attribute name after '.'")
            return ast.AttrRef(first.text, second.text, first.line, first.col)
        return ast.AttrRef(None, first.text, first.line, first.col)

    # -------------------------------------------------------------- conditions

    def parse_condition(self):
        return self._parse_or_cond()

    def _parse_or_cond(self):
        left = self._parse_and_cond()
        while self.check_kw("or"):
            self.advance()
            right = self._parse_and_cond()
            left = ast.Or(left, right)
        return left

    def _parse_and_cond(self):
        left = self._parse_not_cond()
        while self.check_kw("and"):
            self.advance()
            right = self._parse_not_cond()
            left = ast.And(left, right)
        return left

    def _parse_not_cond(self):
        if self.check_kw("not"):
            self.advance()
            return ast.Not(self._parse_not_cond())
        return self._parse_cond_primary()

    def _parse_cond_primary(self):
        if self.check(TokType.LPAREN):
            self.advance()
            inner = self.parse_condition()
            self.expect(TokType.RPAREN, "')' to close parenthesized condition")
            return inner
        return self._parse_comparison()

    def _parse_comparison(self):
        left = self._parse_operand()
        tok = self.cur()
        op_map = {TokType.ASSIGN: "=", TokType.NEQ: "!=", TokType.LT: "<",
                  TokType.LTE: "<=", TokType.GT: ">", TokType.GTE: ">="}
        if tok.type not in op_map:
            raise ParseError(
                f"expected a comparison operator (=, !=, <, <=, >, >=), "
                f"found {_describe(tok)}", tok.line, tok.col)
        self.advance()
        right = self._parse_operand()
        return ast.Comparison(op_map[tok.type], left, right, tok.line, tok.col)

    def _parse_operand(self):
        tok = self.cur()
        if tok.type == TokType.NUMBER:
            self.advance()
            return ast.NumLit(tok.value)
        if tok.type == TokType.STRING:
            self.advance()
            return ast.StrLit(tok.value)
        if tok.type == TokType.IDENT:
            return self._parse_attr_ref()
        raise ParseError(f"expected a number, string, or attribute name, "
                          f"found {_describe(tok)}", tok.line, tok.col)


def _describe(tok):
    if tok.type == TokType.EOF:
        return "end of input"
    if tok.type == TokType.NEWLINE:
        return "end of line"
    return f"'{tok.text}'"


# --------------------------------------------------------------- entry points

def parse_program(tokens):
    return Parser(tokens).parse_program()


def parse_query(tokens):
    p = Parser(tokens)
    p._skip_newlines()
    if p.check(TokType.EOF):
        return None
    q = p.parse_expr()
    p._skip_newlines()
    p.expect(TokType.EOF, "end of input")
    return q
