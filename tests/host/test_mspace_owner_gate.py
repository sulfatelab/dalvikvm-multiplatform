import json
from pathlib import Path
import runpy
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "tests/support/windows/mspace_owner_gate.py"


def test_mspace_owner_gate_records_success_and_four_death_cases(
    tmp_path, monkeypatch
):
    namespace = runpy.run_path(str(RUNNER), run_name="mspace_owner_runner")
    fake = tmp_path / "fake_probe.exe"
    fake.write_bytes(b"regular test placeholder")
    markers = {
        "success": "W013_MSPACE_OWNER_PASS first_calls=5 second_calls=2",
        "missing-provider": "Unattached ART mspace",
        "use-after-detach": "Unattached ART mspace",
        "wrong-owner-detach": "state->extp == provider",
        "double-attach": "state->extp == nullptr",
    }
    seen_modes = []

    def fake_run(command, **kwargs):
        mode = command[-1]
        seen_modes.append(mode)
        assert command == [str(fake), mode]
        assert kwargs["cwd"] == fake.parent
        assert kwargs["shell"] is False
        assert kwargs["timeout"] == 5
        return SimpleNamespace(
            stdout="",
            stderr=markers[mode],
            returncode=0 if mode == "success" else 3,
        )

    monkeypatch.setattr(namespace["subprocess"], "run", fake_run)
    result_path = tmp_path / "result" / "result.json"

    record = namespace["run_gate"](
        target_id="windows-x86_64-msvc",
        probe=fake,
        result_path=result_path,
        library_dirs=[],
        timeout=5,
    )

    assert record["success_cases"] == 1
    assert record["death_cases"] == 4
    assert [case["mode"] for case in record["cases"]] == [
        "success",
        "missing-provider",
        "use-after-detach",
        "wrong-owner-detach",
        "double-attach",
    ]
    assert seen_modes == [case["mode"] for case in record["cases"]]
    assert json.loads(result_path.read_text(encoding="utf-8")) == record
    assert str(tmp_path) not in result_path.read_text(encoding="utf-8")
