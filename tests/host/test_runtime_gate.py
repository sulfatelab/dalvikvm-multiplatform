from pathlib import Path
import importlib.util
import subprocess
import sys
from types import SimpleNamespace

import pytest


_RUNTIME_GATE_PATH = Path(__file__).parents[1] / "support" / "runtime_gate.py"
_SPEC = importlib.util.spec_from_file_location("art_runtime_gate", _RUNTIME_GATE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
runtime_gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(runtime_gate)


def test_elf_needed_reads_host_python_without_external_tools():
    executable = Path(sys.executable).resolve()
    if executable.read_bytes()[:4] != b"\x7fELF":
        pytest.skip("host Python is not ELF")
    assert runtime_gate._elf_needed(executable)


def test_elf_needed_rejects_non_elf(tmp_path):
    artifact = tmp_path / "artifact"
    artifact.write_bytes(b"not an elf")
    with pytest.raises(runtime_gate.GateError, match="not an ELF artifact"):
        runtime_gate._elf_needed(artifact)


def test_show_version_requires_exit_zero_and_marker(tmp_path, monkeypatch, capsys):
    dalvikvm = tmp_path / "dalvikvm"
    dalvikvm.write_bytes(b"placeholder")
    commands = []

    def run(command, **kwargs):
        commands.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="ART version test\n")

    monkeypatch.setattr(subprocess, "run", run)
    runtime_gate.run_show_version(dalvikvm, "ART version test")

    assert commands[0][0] == [str(dalvikvm), "-showversion"]
    assert commands[0][1]["shell"] is False
    assert capsys.readouterr().out == "ART version test\n"


def test_managed_gate_uses_isolated_runtime_and_records_result(
    tmp_path, monkeypatch, capsys
):
    dalvikvm = tmp_path / "bin" / "dalvikvm"
    boot = tmp_path / "managed" / "boot.jar"
    app = tmp_path / "managed" / "hello.jar"
    icu = tmp_path / "source" / "icudt72l.dat"
    for path, content in (
        (dalvikvm, b"vm"),
        (boot, b"boot"),
        (app, b"app"),
        (icu, b"icu"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    commands = []

    def run(command, **kwargs):
        commands.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout="Hello from dalvikvm!\nmain end exception=0\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", run)
    work = tmp_path / "out" / "tests" / "results" / "hello"
    runtime_gate.run_managed(
        target_id="linux-x86_64-gnu",
        dalvikvm=dalvikvm,
        boot_jar=boot,
        app_jar=app,
        main_class="Hello",
        work_root=work,
        icu_data=icu,
        library_dirs=[dalvikvm.parent],
        vm_options=["-Xint"],
        main_args=[],
        expected=["Hello from dalvikvm!", "main end exception=0"],
        forbidden=["AssertionError"],
        expected_exit=0,
        timeout=30,
    )

    command, options = commands[0]
    assert command[0] == str(dalvikvm)
    assert "-Xint" in command
    assert options["shell"] is False
    assert options["env"]["ANDROID_ROOT"] == str(work / "runtime")
    assert (work / "runtime" / "icu" / "icudt72l.dat").read_bytes() == b"icu"
    result = (work / "result.json").read_text(encoding="utf-8")
    assert '"target_id": "linux-x86_64-gnu"' in result
    assert str(tmp_path) not in result
    assert "Hello passed" in capsys.readouterr().out


def test_managed_gate_fails_closed_on_missing_marker(tmp_path, monkeypatch):
    files = []
    for name in ("dalvikvm", "boot.jar", "app.jar", "icudt72l.dat"):
        path = tmp_path / name
        path.write_bytes(name.encode())
        files.append(path)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(
            returncode=0, stdout="unexpected\n", stderr=""
        ),
    )
    with pytest.raises(runtime_gate.GateError, match="missing=.*required marker"):
        runtime_gate.run_managed(
            target_id="linux-x86_64-gnu",
            dalvikvm=files[0],
            boot_jar=files[1],
            app_jar=files[2],
            main_class="Probe",
            work_root=tmp_path / "work",
            icu_data=files[3],
            library_dirs=[tmp_path],
            vm_options=[],
            main_args=[],
            expected=["required marker"],
            forbidden=[],
            expected_exit=0,
            timeout=30,
        )
