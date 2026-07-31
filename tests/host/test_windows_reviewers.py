from pathlib import Path
import runpy


REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEWER_ROOT = REPO_ROOT / "tests" / "support" / "windows"


def test_windows_reviewers_are_python_owned_and_syntax_valid():
    reviewers = sorted(REVIEWER_ROOT.glob("check_*.py"))
    assert len(reviewers) == 7
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


def test_w013_source_policy_matches_current_product_inventory():
    namespace = runpy.run_path(
        str(REVIEWER_ROOT / "check_w013_source_policy.py"),
        run_name="windows_w013_source_reviewer",
    )
    counts = namespace["check_repository"](REPO_ROOT)
    assert counts == {
        "low_address_files": 8,
        "page_transition_files": 4,
        "mspace_lock_assertions": 2,
    }
