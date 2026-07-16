"""Tests for dependency-closure resolution."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bp2cmake.closure import dependency_closure
from bp2cmake.config import Config
from bp2cmake.evaluator import Evaluator
from bp2cmake.overlay import Overlay, GlobalPolicy, ModulePolicy


def _ev(text):
    e = Evaluator(Config())
    e.add_file(text, "<test>/Android.bp")
    return e


def test_simple_chain_order():
    # c -> b -> a ; closure of c is [a, b, c] (deps first)
    e = _ev('''
        cc_library { name: "liba", srcs: ["a.cc"] }
        cc_library { name: "libb", srcs: ["b.cc"], shared_libs: ["liba"] }
        cc_library { name: "libc", srcs: ["c.cc"], shared_libs: ["libb"] }
    ''')
    ov = Overlay(modules={
        "liba": ModulePolicy(kind="shared"),
        "libb": ModulePolicy(kind="shared"),
        "libc": ModulePolicy(kind="shared"),
    })
    assert dependency_closure(e, ov, ["libc"]) == ["liba", "libb", "libc"]


def test_host_libs_skipped():
    e = _ev('''
        cc_library { name: "libx", srcs: ["x.cc"], shared_libs: ["libz", "liba"] }
        cc_library { name: "liba", srcs: ["a.cc"] }
    ''')
    ov = Overlay(global_policy=GlobalPolicy(host_libs=["libz"]))
    out = dependency_closure(e, ov, ["libx"])
    assert "libz" not in out          # host lib skipped
    assert out == ["liba", "libx"]


def test_header_only_dep_skipped():
    # a header lib (no srcs) is not emitted.
    e = _ev('''
        cc_library_headers { name: "libh", export_include_dirs: ["include"] }
        cc_library { name: "libx", srcs: ["x.cc"], header_libs: ["libh"] }
    ''')
    out = dependency_closure(e, Overlay(), ["libx"])
    assert out == ["libx"]


def test_absorbed_whole_static_not_emitted_but_deps_followed():
    # x absorbs w (whole_static); w links a. w is NOT emitted; a IS.
    e = _ev('''
        cc_library_static { name: "libw", srcs: ["w.cc"], shared_libs: ["liba"] }
        cc_library { name: "liba", srcs: ["a.cc"] }
        cc_library { name: "libx", srcs: ["x.cc"], whole_static_libs: ["libw"] }
    ''')
    ov = Overlay(modules={"libx": ModulePolicy(kind="shared", absorb_whole_static=True)})
    out = dependency_closure(e, ov, ["libx"])
    assert "libw" not in out          # absorbed -> not standalone
    assert "liba" in out              # but its transitive dep is emitted
    assert "libx" in out


def test_overlay_added_dep_followed():
    # x has no .bp dep on a, but the overlay adds it -> a is in the closure.
    e = _ev('''
        cc_library { name: "libx", srcs: ["x.cc"] }
        cc_library { name: "liba", srcs: ["a.cc"] }
    ''')
    ov = Overlay(modules={"libx": ModulePolicy(add_shared_libs=["liba"])})
    out = dependency_closure(e, ov, ["libx"])
    assert "liba" in out


def test_cycle_tolerated():
    # ART has shared-lib cycles; the walk must not infinite-loop.
    e = _ev('''
        cc_library { name: "liba", srcs: ["a.cc"], shared_libs: ["libb"] }
        cc_library { name: "libb", srcs: ["b.cc"], shared_libs: ["liba"] }
    ''')
    out = dependency_closure(e, Overlay(), ["liba"])
    assert set(out) == {"liba", "libb"}
