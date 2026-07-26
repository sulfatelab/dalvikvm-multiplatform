from bp2cmake.config import Config
from bp2cmake.emitter import Emitter
from bp2cmake.evaluator import Evaluator
from bp2cmake.overlay import GlobalPolicy, Overlay


def test_global_ldflags_reach_linked_targets_but_not_static_archives():
    evaluator = Evaluator(Config(os="windows"))
    evaluator.add_file(
        """
        cc_library_shared { name: "shared", srcs: ["shared.cc"] }
        cc_library_static { name: "static", srcs: ["static.cc"] }
        cc_binary { name: "program", srcs: ["main.cc"] }
        """,
        "<test>",
    )
    overlay = Overlay(
        global_policy=GlobalPolicy(add_ldflags=["LINKER:/CETCOMPAT:NO"])
    )
    emitter = Emitter(evaluator, overlay)

    shared = emitter.emit_module(evaluator.resolve("shared"))
    static = emitter.emit_module(evaluator.resolve("static"))
    program = emitter.emit_module(evaluator.resolve("program"))

    assert "target_link_options(shared PRIVATE LINKER:/CETCOMPAT:NO)" in shared
    assert "CETCOMPAT" not in static
    assert "target_link_options(program PRIVATE LINKER:/CETCOMPAT:NO)" in program
