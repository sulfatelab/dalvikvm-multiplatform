from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_art_and_art_compiler_do_not_use_cmake_auto_export():
    cmake = (REPO_ROOT / "native" / "CMakeLists.txt").read_text(encoding="utf-8")
    policy = re.search(
        r'if\(ART_TARGET_PLATFORM STREQUAL "windows" AND\s+'
        r'_ttype STREQUAL "SHARED_LIBRARY" AND\s+'
        r'NOT _t STREQUAL "art" AND NOT _t STREQUAL "art-compiler"\)\s+'
        r'.*?WINDOWS_EXPORT_ALL_SYMBOLS ON\)',
        cmake,
        flags=re.DOTALL,
    )
    assert policy is not None


def test_thread_uses_narrow_pe_exports_and_keeps_tls_private():
    thread = (REPO_ROOT / "vendor" / "art" / "runtime" / "thread.h").read_text(
        encoding="utf-8"
    )
    assert "class ART_VISIBILITY_EXPORT Thread {" in thread
    assert "class EXPORT Thread {" not in thread
    tls = re.search(r"^\s*static thread_local Thread\* self_tls_;$", thread, re.MULTILINE)
    assert tls is not None
    assert "EXPORT" not in tls.group(0)


def test_pe_export_macro_has_an_explicit_producer_consumer_boundary():
    macros = (
        REPO_ROOT / "vendor" / "art" / "libartbase" / "base" / "macros.h"
    ).read_text(encoding="utf-8")
    assert "#define EXPORT __declspec(dllexport)" in macros
    assert "#define ART_VISIBILITY_EXPORT" in macros
    assert "#define LIBART_PE_DATA __declspec(dllimport)" in macros
    assert "#define LIBART_PE_API __declspec(dllimport)" in macros


def test_optimized_pe_inline_specializations_have_one_explicit_owner():
    cmake = (REPO_ROOT / "native" / "CMakeLists.txt").read_text(encoding="utf-8")
    source = (
        REPO_ROOT / "compat" / "src" / "art_pe_inline_exports.cc"
    ).read_text(encoding="utf-8")
    assert 'target_sources(art PRIVATE "${_repo}/compat/src/art_pe_inline_exports.cc")' in cmake
    assert "ArtMethod::GetDeclaringClass<kWithReadBarrier>()" in source
    assert "Object::SetField32<false, false, kVerifyNone, false>" in source
    assert "Object::SetField32<false, true, kVerifyNone, false>" in source


def test_jvmti_uses_a_bounded_source_level_art_export_boundary():
    cmake = (REPO_ROOT / "native" / "CMakeLists.txt").read_text(encoding="utf-8")
    codegen = (
        REPO_ROOT / "tools" / "bp2cmake" / "bp2cmake" / "codegen.py"
    ).read_text(encoding="utf-8")
    assert "art/runtime/thread.h" in codegen
    assert "art/runtime/art_method.h" in codegen
    assert codegen.count("EXPORT LIBART_PE_API") == 23
    assert '"LINKER:/EXPORT:mspace_malloc"' in cmake
    assert '"LINKER:/EXPORT:mspace_usable_size"' in cmake


def test_w003_variant_links_internal_counters_but_exports_only_probe_api():
    cmake = (REPO_ROOT / "native" / "CMakeLists.txt").read_text(encoding="utf-8")
    quick = (
        REPO_ROOT
        / "vendor"
        / "art"
        / "runtime"
        / "arch"
        / "x86_64"
        / "quick_entrypoints_x86_64.S"
    ).read_text(encoding="utf-8")
    for symbol in (
        "art_w003_frame_probe_refs_only",
        "art_w003_frame_probe_refs_and_args",
        "art_w003_frame_probe_all_callee_saves",
        "art_w003_frame_probe_everything",
    ):
        assert f".globl {symbol}" in quick
        assert f"LINKER:/EXPORT:{symbol}" not in cmake
    for symbol in (
        "art_w003_frame_probe_reset",
        "art_w003_frame_probe_snapshot",
    ):
        assert f'"LINKER:/EXPORT:{symbol}"' in cmake

    reviewer = (
        REPO_ROOT / "tests" / "support" / "windows" / "check_w003_quick_boundaries.py"
    ).read_text(encoding="utf-8")
    assert "len(win_traps) != 212" not in reviewer
    assert "sum(win_traps.values()) != 401" not in reviewer
