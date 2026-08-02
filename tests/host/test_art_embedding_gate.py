from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


_RUNNER_PATH = (
    Path(__file__).parents[1] / "cases" / "art-embedding" / "run.py"
)
_SPEC = importlib.util.spec_from_file_location("art_embedding_gate", _RUNNER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
art_embedding_gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(art_embedding_gate)


def _successful_output() -> tuple[str, str]:
    stdout = "\n".join(
        [
            "WIN32_ART_EMBED start",
            "WIN32_ART_EMBED runtime_create result=0 vm=1 env=2",
            "WIN32_ART_EMBED predecessor_uef armed=1",
            "WIN32_ART_EMBED predecessor_uef resumed calls=1",
            "WIN32_ART_EMBED frame_seh armed phase=runtime-active",
            "WIN32_ART_EMBED frame_seh caught phase=runtime-active",
            "WIN32_ART_EMBED late_uef installed predecessor_is_art=1",
            "WIN32_ART_EMBED runtime_destroy detach=0 destroy=0",
            "WIN32_ART_EMBED teardown late_uef_preserved=1",
            "WIN32_ART_EMBED frame_seh armed phase=runtime-unloaded",
            "WIN32_ART_EMBED frame_seh caught phase=runtime-unloaded",
            "WIN32_ART_EMBED result foreign_veh_calls=3 "
            "predecessor_uef_calls=1 late_uef_calls=0 frame_seh_calls=2",
            "WIN32_ART_EMBED PASS",
        ]
    )
    stderr = "\n".join(
        [
            "WIN32_ART_EMBED foreign_veh search=1",
            "WIN32_ART_EMBED predecessor_uef continue=1",
            "WIN32_ART_EMBED foreign_veh search=1",
            "WIN32_ART_EMBED foreign_veh search=1",
            "ART Win32 crash: minidump written to C:\\ignored\\art-test.dmp",
        ]
    )
    return stdout + "\n", stderr + "\n"


def test_art_embedding_gate_stages_regular_runtime_and_sanitizes_result(
    tmp_path, monkeypatch, capsys
):
    probe = tmp_path / "win32_art_embedding_probe.exe"
    boot_jar = tmp_path / "source-boot.jar"
    icu_data = tmp_path / "icudt72l.dat"
    library_dir = tmp_path / "dll"
    work_root = tmp_path / "result"
    probe.write_bytes(b"MZ-probe")
    boot_jar.write_bytes(b"boot")
    icu_data.write_bytes(b"icu")
    library_dir.mkdir()
    for name in ("art.dll", "icu_jni.dll", "javacore.dll", "openjdk.dll"):
        (library_dir / name).write_bytes(f"MZ-{name}".encode())
    calls: list[dict[str, object]] = []
    stdout, stderr = _successful_output()

    def fake_run(command, **kwargs):
        calls.append({"command": command, **kwargs})
        crash = kwargs["cwd"] / "run" / "crash" / "art-test.dmp"
        crash.write_bytes(b"dump")
        return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(art_embedding_gate.subprocess, "run", fake_run)
    monkeypatch.setenv("SystemRoot", r"C:\Windows")
    art_embedding_gate.run_gate(
        target_id="windows-x86_64-msvc",
        probe=probe,
        boot_jar=boot_jar,
        work_root=work_root,
        icu_data=icu_data,
        library_dirs=[library_dir],
        repetitions=2,
        timeout=30,
    )

    assert len(calls) == 2
    assert all(call["shell"] is False for call in calls)
    assert [call["cwd"] for call in calls] == [
        work_root / "runs" / "001",
        work_root / "runs" / "002",
    ]
    assert calls[0]["command"] == [str(work_root / "bin" / probe.name)]
    environment = calls[0]["env"]
    assert environment["PATH"] == f"{work_root / 'bin'};C:\\Windows/System32"
    assert environment["ANDROID_ROOT"] == str(work_root / "runs" / "001" / "run")
    for repetition in ("001", "002"):
        run_root = work_root / "runs" / repetition / "run"
        assert (run_root / "boot.jar").read_bytes() == b"boot"
        assert (run_root / "icu" / icu_data.name).read_bytes() == b"icu"

    result_text = (work_root / "result.json").read_text(encoding="utf-8")
    result = json.loads(result_text)
    assert result["target_id"] == "windows-x86_64-msvc"
    assert result["completed_repetitions"] == 2
    assert result["dump_files"] == [
        "runs/001/run/crash/art-test.dmp",
        "runs/002/run/crash/art-test.dmp",
    ]
    assert [item["name"] for item in result["runtime_libraries"]] == [
        "art.dll",
        "icu_jni.dll",
        "javacore.dll",
        "openjdk.dll",
    ]
    assert str(tmp_path) not in result_text
    assert not any(path.is_symlink() for path in work_root.rglob("*"))
    assert "repetitions=2, intentional_dumps=2" in capsys.readouterr().out


def test_art_embedding_gate_rejects_unaccepted_target(tmp_path):
    with pytest.raises(
        art_embedding_gate.runtime_gate.GateError,
        match="no accepted runner",
    ):
        art_embedding_gate.run_gate(
            target_id="windows-aarch64-msvc",
            probe=tmp_path / "missing.exe",
            boot_jar=tmp_path / "missing.jar",
            work_root=tmp_path / "result",
            icu_data=tmp_path / "missing.dat",
            library_dirs=[],
            repetitions=1,
            timeout=1,
        )


def test_art_embedding_output_requires_exact_exception_counts():
    stdout, stderr = _successful_output()
    missing, forbidden, count_errors = art_embedding_gate._validate_output(
        stdout + stderr.replace(
            "WIN32_ART_EMBED foreign_veh search=1\n",
            "",
            1,
        )
    )
    assert missing == []
    assert forbidden == []
    assert count_errors == [
        "'WIN32_ART_EMBED foreign_veh search=1': expected 3, found 2"
    ]
