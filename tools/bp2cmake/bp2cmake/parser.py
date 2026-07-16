"""Recursive-descent parser for Blueprint (.bp) files.

Grammar (informal):

    file        := statement*
    statement   := assignment | module
    assignment  := IDENT ('=' | '+=') expr
    module      := IDENT map
    map         := '{' ( IDENT ':' expr ','? )* '}'
    list        := '[' ( expr ','? )* ']'
    expr        := operand ( '+' operand )*
    operand     := STRING | NUMBER | bool | VarRef | list | map | select
    select      := 'select' '(' conds ',' '{' case* '}' ','? ')'
    conds       := condition | '(' condition ( ',' condition )* ')'
    condition   := IDENT '(' STRING* ')'
    case        := patterns ':' expr ','?
    patterns    := pattern | '(' pattern ( ',' pattern )* ')'
    pattern     := STRING | 'true' | 'false' | ('default'|'any') ('@' IDENT)?
                 | IDENT      (rare bare-ident literal)
    bool        := 'true' | 'false'
    VarRef      := IDENT (that is not 'true'/'false')

Trailing commas are allowed in lists and maps. Top-level module property
bags use the same map syntax.
"""

from __future__ import annotations

from . import ast
from .lexer import Token, tokenize


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens: list[Token], filename: str = "<bp>"):
        self.toks = tokens
        self.pos = 0
        self.filename = filename

    # --- token helpers -------------------------------------------------

    @property
    def cur(self) -> Token:
        return self.toks[self.pos]

    def _err(self, msg: str, tok: Token | None = None) -> ParseError:
        t = tok or self.cur
        return ParseError(f"{self.filename}:{t.line}:{t.col}: {msg} (got {t.kind} {t.value!r})")

    def advance(self) -> Token:
        t = self.toks[self.pos]
        if t.kind != "EOF":
            self.pos += 1
        return t

    def expect(self, kind: str) -> Token:
        if self.cur.kind != kind:
            raise self._err(f"expected {kind}")
        return self.advance()

    def accept(self, kind: str) -> Token | None:
        if self.cur.kind == kind:
            return self.advance()
        return None

    # --- top level -----------------------------------------------------

    def parse_file(self) -> ast.BlueprintFile:
        bp = ast.BlueprintFile(path=self.filename)
        while self.cur.kind != "EOF":
            bp.statements.append(self.parse_statement())
        return bp

    def parse_statement(self):
        if self.cur.kind != "IDENT":
            raise self._err("expected a module type or variable name")
        name_tok = self.advance()

        # assignment?
        if self.cur.kind in ("EQUALS", "PLUSEQ"):
            op = self.advance()
            value = self.parse_expr()
            return ast.Assignment(
                name=name_tok.value,
                value=value,
                append=(op.kind == "PLUSEQ"),
                line=name_tok.line,
            )

        # otherwise a module: IDENT '{' ... '}'
        if self.cur.kind == "LBRACE":
            props = self.parse_map()
            return ast.Module(type=name_tok.value, properties=props, line=name_tok.line)

        raise self._err("expected '=', '+=' or '{' after identifier", name_tok)

    # --- expressions ---------------------------------------------------

    def parse_expr(self) -> ast.Expr:
        left = self.parse_operand()
        while self.cur.kind == "PLUS":
            plus = self.advance()
            right = self.parse_operand()
            left = ast.Concat(left=left, right=right, line=plus.line)
        return left

    def parse_operand(self) -> ast.Expr:
        t = self.cur
        if t.kind == "STRING":
            self.advance()
            return ast.StringLit(value=t.value, line=t.line)
        if t.kind == "NUMBER":
            self.advance()
            return ast.IntLit(value=int(t.value), line=t.line)
        if t.kind == "LBRACK":
            return self.parse_list()
        if t.kind == "LBRACE":
            return self.parse_map()
        if t.kind == "IDENT":
            if t.value == "select" and self.toks[self.pos + 1].kind == "LPAREN":
                return self.parse_select()
            self.advance()
            if t.value == "true":
                return ast.BoolLit(True, line=t.line)
            if t.value == "false":
                return ast.BoolLit(False, line=t.line)
            return ast.VarRef(name=t.value, line=t.line)
        raise self._err("expected a value")

    # --- select() expressions (Soong) ----------------------------------

    def parse_select(self) -> ast.Select:
        """select(cond, {pat: val, ...}) or select((c1, c2), {(p1,p2): val,...})."""
        kw = self.expect("IDENT")  # 'select'
        self.expect("LPAREN")
        # Conditions: either a single func() call, or a parenthesized tuple.
        conditions: list[tuple[str, list[str]]] = []
        if self.cur.kind == "LPAREN":
            self.advance()
            while self.cur.kind != "RPAREN":
                conditions.append(self.parse_condition())
                if not self.accept("COMMA"):
                    break
            self.expect("RPAREN")
        else:
            conditions.append(self.parse_condition())
        self.expect("COMMA")
        cases = self.parse_select_cases(len(conditions))
        self.accept("COMMA")  # trailing comma after the cases map
        self.expect("RPAREN")
        return ast.Select(conditions=conditions, cases=cases, line=kw.line)

    def parse_condition(self) -> tuple[str, list[str]]:
        """A condition function call: IDENT '(' STRING* ')', e.g.
        soong_config_variable("ns", "var"), os(), release_flag("X")."""
        fn = self.expect("IDENT")
        self.expect("LPAREN")
        args: list[str] = []
        while self.cur.kind != "RPAREN":
            args.append(self.expect("STRING").value)
            if not self.accept("COMMA"):
                break
        self.expect("RPAREN")
        return (fn.value, args)

    def parse_select_cases(self, n_conds: int) -> list[ast.SelectCase]:
        self.expect("LBRACE")
        cases: list[ast.SelectCase] = []
        while self.cur.kind != "RBRACE":
            patterns, binding = self.parse_case_patterns(n_conds)
            self.expect("COLON")
            value = self.parse_expr()
            cases.append(ast.SelectCase(patterns=patterns, value=value,
                                        binding=binding, line=value.line))
            if not self.accept("COMMA"):
                break
        self.expect("RBRACE")
        return cases

    def parse_case_patterns(self, n_conds: int) -> tuple[list[object], str | None]:
        """Parse one case's key: a single pattern, or a (p1, p2, ...) tuple.
        Returns (patterns, binding) where binding is the `any @ name` capture."""
        if self.cur.kind == "LPAREN":
            self.advance()
            pats: list[object] = []
            binding: str | None = None
            while self.cur.kind != "RPAREN":
                p, b = self.parse_single_pattern()
                pats.append(p)
                if b is not None:
                    binding = b
                if not self.accept("COMMA"):
                    break
            self.expect("RPAREN")
            return pats, binding
        p, b = self.parse_single_pattern()
        return [p], b

    def parse_single_pattern(self) -> tuple[object, str | None]:
        """A single pattern: STRING | true | false | default | any [@ name]."""
        t = self.cur
        if t.kind == "STRING":
            self.advance()
            return t.value, None
        if t.kind == "IDENT":
            self.advance()
            binding: str | None = None
            if self.cur.kind == "AT":
                self.advance()
                binding = self.expect("IDENT").value
            if t.value == "true":
                return True, binding
            if t.value == "false":
                return False, binding
            if t.value == "any":
                return ast.ANY, binding
            if t.value == "default":
                return ast.DEFAULT, binding
            # Any other bare ident pattern (rare) -> treat as a literal match.
            return t.value, binding
        raise self._err("expected a select pattern")

    def parse_list(self) -> ast.ListExpr:
        lb = self.expect("LBRACK")
        items: list[ast.Expr] = []
        while self.cur.kind != "RBRACK":
            items.append(self.parse_expr())
            if not self.accept("COMMA"):
                # no comma -> must be end of list
                break
        self.expect("RBRACK")
        return ast.ListExpr(items=items, line=lb.line)

    def parse_map(self) -> ast.MapExpr:
        lb = self.expect("LBRACE")
        entries: list[tuple[str, ast.Expr]] = []
        while self.cur.kind != "RBRACE":
            key = self.expect("IDENT")
            self.expect("COLON")
            value = self.parse_expr()
            entries.append((key.value, value))
            if not self.accept("COMMA"):
                break
        self.expect("RBRACE")
        return ast.MapExpr(entries=entries, line=lb.line)


def parse(text: str, filename: str = "<bp>") -> ast.BlueprintFile:
    return Parser(tokenize(text, filename), filename).parse_file()
