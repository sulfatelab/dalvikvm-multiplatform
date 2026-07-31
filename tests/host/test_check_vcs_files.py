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
