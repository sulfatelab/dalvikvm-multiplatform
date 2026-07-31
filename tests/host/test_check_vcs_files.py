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
    assert len(source_cases) == 28
    assert all((case / "RESULT.md").is_file() for case in source_cases)


def test_managed_java_sources_are_case_owned_with_adjacent_results():
    case_root = REPO_ROOT / "tests" / "cases"
    java_sources = sorted(case_root.glob("*/*.java"))
    assert len(java_sources) == 48
    assert all((source.parent / "RESULT.md").is_file() for source in java_sources)
    assert not list((REPO_ROOT / "tools" / "verify").glob("**/*.java"))
