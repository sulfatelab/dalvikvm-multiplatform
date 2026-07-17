"""Tests for the Blueprint lexer + parser."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bp2cmake import ast
from bp2cmake.parser import parse


def test_simple_module():
    bp = parse('cc_library { name: "foo", srcs: ["a.cpp", "b.cpp"] }')
    assert len(bp.modules) == 1
    m = bp.modules[0]
    assert m.type == "cc_library"
    name = m.properties.get("name")
    assert isinstance(name, ast.StringLit) and name.value == "foo"
    srcs = m.properties.get("srcs")
    assert isinstance(srcs, ast.ListExpr)
    assert [s.value for s in srcs.items] == ["a.cpp", "b.cpp"]


def test_bools_and_ints():
    bp = parse('x { a: true, b: false, c: 29, d: -3 }')
    m = bp.modules[0]
    assert isinstance(m.properties.get("a"), ast.BoolLit)
    assert m.properties.get("a").value is True
    assert m.properties.get("b").value is False
    assert m.properties.get("c").value == 29
    assert m.properties.get("d").value == -3


def test_assignment_and_varref():
    bp = parse('foo = ["a.cpp"]\nbar { srcs: foo }')
    assert len(bp.assignments) == 1
    assn = bp.assignments[0]
    assert assn.name == "foo" and assn.append is False
    ref = bp.modules[0].properties.get("srcs")
    assert isinstance(ref, ast.VarRef) and ref.name == "foo"


def test_append_assignment():
    bp = parse('foo = ["a"]\nfoo += ["b"]')
    assert bp.assignments[1].append is True


def test_concat():
    bp = parse('x { s: "a" + "b", l: ["a"] + other }')
    m = bp.modules[0]
    s = m.properties.get("s")
    assert isinstance(s, ast.Concat)
    assert isinstance(s.left, ast.StringLit) and s.left.value == "a"
    assert isinstance(s.right, ast.StringLit) and s.right.value == "b"
    l = m.properties.get("l")
    assert isinstance(l, ast.Concat)
    assert isinstance(l.right, ast.VarRef) and l.right.name == "other"


def test_nested_maps_and_trailing_commas():
    text = """
    cc_defaults {
        name: "d",
        target: {
            linux: {
                srcs: ["errors_unix.cpp",],
            },
            windows: {
                srcs: ["errors_windows.cpp"],
                enabled: true,
            },
        },
    }
    """
    bp = parse(text)
    m = bp.modules[0]
    target = m.properties.get("target")
    assert isinstance(target, ast.MapExpr)
    linux = target.get("linux")
    assert isinstance(linux, ast.MapExpr)
    srcs = linux.get("srcs")
    assert [s.value for s in srcs.items] == ["errors_unix.cpp"]


def test_comments_skipped():
    text = """
    // line comment
    cc_library { /* inline */ name: "foo" } // trailing
    """
    bp = parse(text)
    assert bp.modules[0].properties.get("name").value == "foo"


def test_string_escapes():
    bp = parse(r'x { s: "a\"b\n" }')
    assert bp.modules[0].properties.get("s").value == 'a"b\n'


def test_real_libbase_bp():
    """Parse nested vendor/libbase Android.bp end-to-end (pure multipath)."""
    _repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    archive = os.path.join(_repo, "vendor", "libbase", "Android.bp")
    if not os.path.exists(archive):
        return  # skip if vendor/libbase not present
    with open(archive) as f:
        bp = parse(f.read(), archive)
    names = []
    for m in bp.modules:
        n = m.properties.get("name")
        if isinstance(n, ast.StringLit):
            names.append(n.value)
    # Spot-check the modules we care about are all present.
    for expected in ["libbase", "libbase_headers", "libbase_defaults",
                     "libbase_cflags_defaults", "system_libbase_license"]:
        assert expected in names, f"missing module {expected}"
