"""AST node types for parsed Blueprint files.

The parser produces *unevaluated* nodes: variable references and `+`
concatenations are preserved as nodes so the evaluator (Layer 1) can resolve
them later with full scope. Literal values use plain Python types where there
is no ambiguity (str, int, bool), wrapped only when position/operators matter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

# A value expression is one of these node types or a literal.
Expr = Union[
    "StringLit",
    "BoolLit",
    "IntLit",
    "VarRef",
    "ListExpr",
    "MapExpr",
    "Concat",
    "Select",
]


@dataclass
class StringLit:
    value: str
    line: int = 0


@dataclass
class BoolLit:
    value: bool
    line: int = 0


@dataclass
class IntLit:
    value: int
    line: int = 0


@dataclass
class VarRef:
    """Reference to a previously assigned variable."""

    name: str
    line: int = 0


@dataclass
class ListExpr:
    items: list[Expr] = field(default_factory=list)
    line: int = 0


@dataclass
class MapExpr:
    """An ordered set of key -> value entries (a Blueprint map / property bag)."""

    entries: list[tuple[str, Expr]] = field(default_factory=list)
    line: int = 0

    def get(self, key: str) -> Expr | None:
        for k, v in self.entries:
            if k == key:
                return v
        return None


@dataclass
class Concat:
    """left + right. Blueprint allows string+string and list+list."""

    left: Expr
    right: Expr
    line: int = 0


@dataclass
class SelectCase:
    """One `pattern: value` arm of a select().

    `patterns` is one entry per condition (a single-condition select has one;
    a tuple select `select((a, b), {...})` has N). Each pattern is one of:
      * a str literal  -> matches that exact condition value,
      * True / False    -> matches the boolean condition value,
      * the sentinel `ANY` (Soong `any`) -> matches any *set* (non-None) value,
      * the sentinel `DEFAULT` (Soong `default`) -> fallback, matches anything
        (including an unset/None condition) but at lowest priority.
    `binding` is the variable name captured by `any @ name` / `default @ name`
    (else None); when set and the case is chosen, occurrences of that VarRef in
    `value` resolve to the matched condition value.
    """

    patterns: list[object]
    value: Expr
    binding: str | None = None
    line: int = 0


# Sentinel patterns. ANY = Soong `any` (matches any set value). DEFAULT = Soong
# `default` (the fallback arm; matches anything incl. unset, lowest priority).
ANY = object()
DEFAULT = object()


@dataclass
class Select:
    """A Soong `select(condition, { pattern: value, ... })` expression.

    `conditions` is the list of condition descriptors (one for a scalar select,
    several for a tuple `select((c1, c2), {...})`). Each descriptor is a
    (func, args) pair, e.g. ("soong_config_variable", ["art_module", "x"]),
    ("os", []), ("release_flag", ["RELEASE_..."]). The evaluator resolves each
    against the fixed Config, then picks the first matching case.
    """

    conditions: list[tuple[str, list[str]]]
    cases: list[SelectCase] = field(default_factory=list)
    line: int = 0


# Top-level statements.


@dataclass
class Assignment:
    name: str
    value: Expr
    append: bool  # True for '+=', False for '='
    line: int = 0


@dataclass
class Module:
    type: str
    properties: MapExpr
    line: int = 0


@dataclass
class BlueprintFile:
    path: str
    statements: list[Union[Assignment, Module]] = field(default_factory=list)

    @property
    def modules(self) -> list[Module]:
        return [s for s in self.statements if isinstance(s, Module)]

    @property
    def assignments(self) -> list[Assignment]:
        return [s for s in self.statements if isinstance(s, Assignment)]
