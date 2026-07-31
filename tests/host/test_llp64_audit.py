from pathlib import Path
import runpy


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_llp64_frontend_replay_removes_old_compile_outputs_and_duplicate_source(
    tmp_path,
):
    source = tmp_path / "probe.c"
    source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
    namespace = runpy.run_path(
        str(REPO_ROOT / "tools" / "llp64_audit" / "scan_compile_db_warnings.py"),
        run_name="llp64_compile_reviewer",
    )
    command = namespace["build_cmd"](
        {
            "file": str(source),
            "directory": str(tmp_path),
            "args": ["clang", "-c", "probe.c", "-o", "probe.obj"],
        },
        ["-Wvoid-pointer-to-int-cast"],
    )

    assert command == [
        "clang",
        "-Wvoid-pointer-to-int-cast",
        "-fsyntax-only",
        str(source),
    ]
