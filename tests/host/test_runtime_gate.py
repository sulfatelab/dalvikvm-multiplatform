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
