from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from check_vcs_files import (  # noqa: E402
    TRACKED_BINARY_EXCEPTIONS,
    forbidden_tracked_paths,
    tracked_paths,
)


def test_binary_and_archive_suffixes_are_rejected_case_insensitively():
    assert forbidden_tracked_paths(
        [
            "out/probe.EXE",
            "tests/evidence/result.zip",
            "tests/cases/example/probe.cc",
        ]
    ) == ["out/probe.EXE", "tests/evidence/result.zip"]


def test_r8_is_the_only_named_binary_exception():
    assert TRACKED_BINARY_EXCEPTIONS == {"vendor/r8/r8.jar"}
    assert forbidden_tracked_paths(TRACKED_BINARY_EXCEPTIONS) == []


def test_repository_index_contains_no_unapproved_binary_or_archive():
    assert forbidden_tracked_paths(tracked_paths(REPO_ROOT)) == []


def test_catalog_native_sources_are_case_owned_with_adjacent_results():
    catalog_source = (REPO_ROOT / "tests" / "CMakeLists.txt").read_text(
        encoding="utf-8"
    )
    assert "tools/verify" not in catalog_source

    case_root = REPO_ROOT / "tests" / "cases"
    source_suffixes = {".c", ".cc", ".cpp", ".S"}
    source_cases = {
        path.parent
        for path in case_root.glob("*/*")
        if path.is_file() and path.suffix in source_suffixes
    }
    assert len(source_cases) == 29
    assert all((case / "RESULT.md").is_file() for case in source_cases)


def test_managed_java_sources_are_case_owned_with_adjacent_results():
    case_root = REPO_ROOT / "tests" / "cases"
    java_sources = sorted(case_root.glob("*/*.java"))
    assert len(java_sources) == 48
    assert all((source.parent / "RESULT.md").is_file() for source in java_sources)
    assert not list((REPO_ROOT / "tools" / "verify").glob("**/*.java"))


def test_retired_windows_libcore_product_paths_do_not_reappear():
    verify_root = REPO_ROOT / "tools" / "verify"
    native_suffixes = {".c", ".cc", ".cpp", ".S"}
    assert not [
        path
        for path in verify_root.rglob("*")
        if path.is_file() and path.suffix in native_suffixes
    ]

    retired = (
        verify_root / "windows_x64_libcore_icu",
        REPO_ROOT / "tools/windows_x64/host_package",
        REPO_ROOT / "tools/windows_x64/stage_native_modules.sh",
        REPO_ROOT / "tools/windows_x64/jni_stubs/build_combined.sh",
        REPO_ROOT / "tools/windows_x64/jni_stubs/native_converter.c",
    )
    assert not [path for path in retired if path.exists() or path.is_symlink()]


def test_retired_checked_linux_product_graph_does_not_reappear():
    retired = (
        REPO_ROOT / "native/generate.sh",
        REPO_ROOT / "native/generated/dalvikvm.cmake",
    )
    assert not [path for path in retired if path.exists() or path.is_symlink()]


def test_native_cmake_modules_are_common_includes_not_entry_points():
    entry = (REPO_ROOT / "native/CMakeLists.txt").read_text(encoding="utf-8")
    modules = {
        "ArtCodegen.cmake",
        "ArtCompatibility.cmake",
        "ArtPlatform.cmake",
        "ArtTargetGraph.cmake",
    }
    assert {path.name for path in (REPO_ROOT / "native/cmake").glob("*.cmake")} == modules
    for name in modules:
        text = (REPO_ROOT / "native/cmake" / name).read_text(encoding="utf-8")
        assert "cmake_minimum_required(" not in text
        assert "project(" not in text
        assert f'/cmake/{name}")' in entry
