from pathlib import Path
import runpy


REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEWER_ROOT = REPO_ROOT / "tests" / "support" / "windows"


def test_windows_reviewers_are_python_owned_and_syntax_valid():
    reviewers = sorted(REVIEWER_ROOT.glob("check_*.py"))
    assert len(reviewers) == 8
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
        "mspace_attachment_tokens": 6,
        "raw_mspace_creation_files": 1,
    }


def test_w013_mspace_policy_rejects_raw_creation_outside_wrapper(tmp_path):
    namespace = runpy.run_path(
        str(REVIEWER_ROOT / "check_w013_source_policy.py"),
        run_name="windows_w013_source_reviewer",
    )
    art = tmp_path / "vendor" / "art"
    allocator = art / "runtime" / "gc" / "allocator" / "art-dlmalloc.cc"
    space = art / "runtime" / "gc" / "space" / "dlmalloc_space.cc"
    bypass = art / "runtime" / "gc" / "space" / "bypass.cc"
    for path in (allocator, space, bypass):
        path.parent.mkdir(parents=True, exist_ok=True)
    allocator.write_text(
        "\n".join(namespace["MSPACE_ATTACHMENT_TOKENS"])
        + "\nvoid* p = create_mspace_with_base(base, size, false);\n",
        encoding="utf-8",
    )
    space.write_text("// direct owner dispatch only\n", encoding="utf-8")
    bypass.write_text("void* p = create_mspace(size, false);\n", encoding="utf-8")

    try:
        namespace["check_mspace_owner_policy"](tmp_path)
    except RuntimeError as error:
        assert "unexpected=['runtime/gc/space/bypass.cc']" in str(error)
    else:
        raise AssertionError("raw mspace creation outside the wrapper was accepted")
