"""Tokenizer for the Blueprint (.bp) grammar.

Blueprint is a small declarative language. The token kinds we need:

    IDENT     foo, cc_library, true, false  (keywords are just idents)
    STRING    "..."  (double-quoted, with \\ escapes)
    NUMBER    123, -7
    LBRACE RBRACE LBRACK RBRACK   { } [ ]
    LPAREN RPAREN                 ( )    (Soong select() conditions/patterns)
    COLON COMMA PLUS EQUALS PLUSEQ AT   : , + = += @
    EOF

Comments (// line, /* block */) and whitespace are skipped.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Token:
    kind: str
    value: str
    line: int
    col: int

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Token({self.kind}, {self.value!r}, {self.line}:{self.col})"


class LexError(Exception):
    pass


_PUNCT = {
    "{": "LBRACE",
    "}": "RBRACE",
    "[": "LBRACK",
    "]": "RBRACK",
    "(": "LPAREN",
    ")": "RPAREN",
    ":": "COLON",
    ",": "COMMA",
    "+": "PLUS",
    "=": "EQUALS",
    "@": "AT",
}


def _is_ident_start(ch: str) -> bool:
    return ch.isalpha() or ch == "_"


def _is_ident_part(ch: str) -> bool:
    return ch.isalnum() or ch in ("_", ".", "-")


def tokenize(text: str, filename: str = "<bp>") -> list[Token]:
    tokens: list[Token] = []
    i = 0
    n = len(text)
    line = 1
    col = 1

    def adv(count: int = 1) -> None:
        nonlocal i, line, col
        for _ in range(count):
            if i < n and text[i] == "\n":
                line += 1
                col = 1
            else:
                col += 1
            i += 1

    while i < n:
        ch = text[i]

        # whitespace
        if ch in " \t\r\n":
            adv()
            continue

        # line comment
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                adv()
            continue

        # block comment
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            start_line, start_col = line, col
            adv(2)
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                adv()
            if i >= n:
                raise LexError(
                    f"{filename}:{start_line}:{start_col}: unterminated block comment"
                )
            adv(2)
            continue

        # string
        if ch == '"':
            start_line, start_col = line, col
            adv()  # opening quote
            buf: list[str] = []
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    nxt = text[i + 1]
                    mapping = {"n": "\n", "t": "\t", "\\": "\\", '"': '"'}
                    buf.append(mapping.get(nxt, nxt))
                    adv(2)
                else:
                    buf.append(text[i])
                    adv()
            if i >= n:
                raise LexError(
                    f"{filename}:{start_line}:{start_col}: unterminated string"
                )
            adv()  # closing quote
            tokens.append(Token("STRING", "".join(buf), start_line, start_col))
            continue

        # += operator
        if ch == "+" and i + 1 < n and text[i + 1] == "=":
            tokens.append(Token("PLUSEQ", "+=", line, col))
            adv(2)
            continue

        # punctuation
        if ch in _PUNCT:
            tokens.append(Token(_PUNCT[ch], ch, line, col))
            adv()
            continue

        # number (optionally signed)
        if ch.isdigit() or (ch == "-" and i + 1 < n and text[i + 1].isdigit()):
            start_line, start_col = line, col
            j = i + 1
            while j < n and text[j].isdigit():
                j += 1
            tokens.append(Token("NUMBER", text[i:j], start_line, start_col))
            adv(j - i)
            continue

        # identifier
        if _is_ident_start(ch):
            start_line, start_col = line, col
            j = i
            while j < n and _is_ident_part(text[j]):
                j += 1
            tokens.append(Token("IDENT", text[i:j], start_line, start_col))
            adv(j - i)
            continue

        raise LexError(f"{filename}:{line}:{col}: unexpected character {ch!r}")

    tokens.append(Token("EOF", "", line, col))
    return tokens
