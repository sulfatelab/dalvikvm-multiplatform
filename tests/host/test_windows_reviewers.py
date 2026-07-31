from pathlib import Path
import runpy


REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEWER_ROOT = REPO_ROOT / "tests" / "support" / "windows"


def test_windows_reviewers_are_python_owned_and_syntax_valid():
    reviewers = sorted(REVIEWER_ROOT.glob("check_*.py"))
    assert len(reviewers) == 6
    assert not list(
        (REPO_ROOT / "tools" / "verify" / "windows_x64_phase1").glob("*.py")
    )
    for reviewer in reviewers:
        assert not reviewer.is_symlink()
        compile(reviewer.read_text(encoding="utf-8"), reviewer.as_posix(), "exec")


def test_cet_source_policy_uses_generated_graph_and_updated_packagers():
    namespace = runpy.run_path(
        str(REVIEWER_ROOT / "check_win32_cet_contract.py"),
        run_name="windows_cet_reviewer",
    )
    raw_links, packagers = namespace["check_source_policy"](REPO_ROOT)
    assert raw_links > 0
    assert packagers > 0
