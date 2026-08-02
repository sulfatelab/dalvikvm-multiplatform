from pathlib import Path

import pytest

from bp2cmake.config import Config
from bp2cmake.emitter import Emitter
from bp2cmake.evaluator import Evaluator
from bp2cmake.overlay import (
    BlueprintScanPolicy,
    GlobalPolicy,
    ModulePolicy,
    Overlay,
    load_overlay_factory,
)
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


def test_blueprint_scan_policy_is_path_free_and_root_typed():
    policy = BlueprintScanPolicy(
        excluded_path_components=("tests", "fuzz"),
        excluded_top_levels=(("ROOT", ("nested",)),),
    )
    assert policy.excludes("ROOT", ("nested", "Android.bp"))
    assert not policy.excludes("OTHER", ("nested", "Android.bp"))
    assert policy.excludes("OTHER", ("module", "tests", "Android.bp"))
    assert policy.to_dict() == {
        "excluded_path_components": ["tests", "fuzz"],
        "excluded_top_levels": {"ROOT": ["nested"]},
    }


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
    assert "cmake -E make_directory" not in text
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
    assert not (repo / "overlay" / "port_policy.py").exists()
    assert not (repo / "overlay" / "port_policy_windows.py").exists()
    linux = load_overlay_factory(str(factory), resolve_target("linux-x86_64-gnu"))
    windows = load_overlay_factory(str(factory), resolve_target("windows-x86_64-msvc"))
    assert len(linux.modules) == 40
    assert len(windows.modules) == 34
    assert linux.global_policy.host_libs == windows.global_policy.host_libs
    assert linux.blueprint_scan == windows.blueprint_scan
    assert linux.blueprint_scan.excludes(
        "MDVM_NATIVE_SRC_ROOT_DIR", ("art", "Android.bp")
    )
    assert not linux.blueprint_scan.excludes(
        "MDVM_ART_ROOT_DIR", ("art", "Android.bp")
    )
    assert linux.global_policy.add_ldflags == []
    assert windows.global_policy.add_ldflags == [
        "LINKER:/CETCOMPAT:NO",
        "LINKER:/DYNAMICBASE",
        "LINKER:/NXCOMPAT",
        "LINKER:/HIGHENTROPYVA",
    ]
    assert "__LP64__=1" not in linux.global_policy.art_defines
    assert "__LP64__=1" in windows.global_policy.art_defines
    assert linux.policy_for("libart-compiler").kind == "shared"
    assert linux.policy_for("libart").add_gensrc_sources == [
        "art/asm/mterp/mterp_x86_64.S"
    ]
    assert windows.policy_for("libart").add_gensrc_sources == [
        "art/asm/mterp/mterp_x86_64.S"
    ]
    assert windows.policy_for("libart-runtime").add_gensrc_sources == [
        "art/asm/mterp/mterp_x86_64.S"
    ]
    for name in ("libcrypto", "libssl", "libjavacrypto"):
        assert linux.policy_for(name).kind == "shared"
        assert windows.policy_for(name).kind == "shared"
    assert windows.policy_for("libjavacrypto").add_shared_libs == [
        "libcrypto",
        "libssl",
    ]
    compiler = windows.policy_for("libart-compiler")
    assert compiler.kind == "shared"
    assert compiler.add_shared_libs == ["libart", "libart-disassembler"]
    dex2oat = windows.policy_for("dex2oat")
    assert dex2oat.kind == "executable"
    assert dex2oat.absorb_whole_static is False
    assert dex2oat.remove_static_libs == ["libdex2oat_static"]
    assert "libart-dex2oat" in dex2oat.add_shared_libs
    art_dex2oat = windows.policy_for("libart-dex2oat")
    assert "MDVM_WINDOWS_DEX2OAT_COMPAT" in art_dex2oat.add_defines
    assert "ART_CONSUMING_LIBART" in art_dex2oat.add_defines
    assert "ART_CONSUMING_LIBART" in dex2oat.add_defines
    icu = windows.policy_for("libicu")
    assert icu.kind == "shared"
    assert "U_SHOW_CPLUSPLUS_API=0" in icu.add_defines
    assert "__INTRODUCED_IN(x)=" in icu.add_defines
    openjdkjvm = windows.policy_for("libopenjdkjvm")
    assert "ART_CONSUMING_LIBART" in openjdkjvm.add_defines
    assert "MDVM_SOCKET_FD_REGISTRY_EXPORTS=1" in openjdkjvm.add_defines
    javacore = windows.policy_for("libjavacore")
    assert "libcore_io_Linux.cpp" in javacore.remove_srcs
    assert "MDVM_WINDOWS_KEEP_CONST_MACRO" in javacore.add_defines
    openjdk = windows.policy_for("libopenjdk")
    assert "LinuxNativeDispatcher.c" in openjdk.remove_srcs
    assert "NativeThread.c" in openjdk.remove_srcs
    with pytest.raises(ValueError, match="no reviewed ART overlay policy"):
        load_overlay_factory(str(factory), resolve_target("linux-aarch64-gnu"))
