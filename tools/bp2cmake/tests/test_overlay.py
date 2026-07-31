from pathlib import Path

from bp2cmake.config import Config
from bp2cmake.emitter import Emitter
from bp2cmake.evaluator import Evaluator
from bp2cmake.overlay import GlobalPolicy, ModulePolicy, Overlay, load_overlay_factory
from bp2cmake.target import resolve_target


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


def test_gensrc_command_uses_shell_free_capture_helper():
    evaluator = Evaluator(Config())
    evaluator.add_file(
        """
        python_binary_host { name: "generator", srcs: ["generate.py"] }
        gensrcs {
            name: "generated_cc",
            tools: ["generator"],
            srcs: ["input.h"],
            output_extension: "operator_out.cc",
        }
        cc_library {
            name: "library",
            srcs: ["library.cc"],
            generated_sources: ["generated_cc"],
        }
        """,
        "module/Android.bp",
    )
    text = Emitter(evaluator, Overlay()).emit_module(evaluator.resolve("library"))
    assert "bp2cmake/capture_output.py" in text
    assert " --\n            ${Python3_EXECUTABLE}" in text
    assert " > " not in text


def test_absorbed_whole_static_includes_precede_other_link_dependencies():
    evaluator = Evaluator(Config(os="windows"))
    evaluator.add_file(
        """
        cc_library_static {
            name: "compiler_sources",
            srcs: ["jit/jit_compiler.cc"],
            export_include_dirs: ["."],
        }
        cc_library_static {
            name: "lzma",
            srcs: ["Compiler.c"],
            export_include_dirs: ["C"],
        }
        cc_library {
            name: "runtime",
            srcs: ["runtime.cc"],
            static_libs: ["lzma"],
            whole_static_libs: ["compiler_sources"],
        }
        """,
        "vendor/Android.bp",
    )
    overlay = Overlay(
        modules={"runtime": ModulePolicy(absorb_whole_static=True)}
    )

    text = Emitter(evaluator, overlay).emit_module(evaluator.resolve("runtime"))

    compiler_include = "${MDVM_NATIVE_SRC_ROOT_DIR}/."
    lzma_include = "${MDVM_NATIVE_SRC_ROOT_DIR}/C"
    assert text.index(compiler_include + "\n") < text.index(lzma_include + "\n")


def test_unified_overlay_factory_selects_current_target_policy():
    repo = Path(__file__).resolve().parents[3]
    factory = repo / "overlay" / "art_port_policy.py"
    linux = load_overlay_factory(str(factory), resolve_target("linux-x86_64-gnu"))
    windows = load_overlay_factory(str(factory), resolve_target("windows-x86_64-msvc"))
    assert linux.policy_for("libart-compiler").kind == "shared"
    compiler = windows.policy_for("libart-compiler")
    assert compiler.kind == "shared"
    assert compiler.add_shared_libs == ["libart", "libart-disassembler"]
