from pathlib import Path
import importlib.util
import json
from types import SimpleNamespace


CASES_ROOT = Path(__file__).parents[1] / "cases"


def _load(name: str, relative: str):
    path = CASES_ROOT / relative / "run.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


uef_gate = _load("art_w010_uef_gate", "unhandled-exception-filter")
managed_gate = _load("art_w010_managed_fault_gate", "managed-fault-recovery")
debugger_gate = _load("art_w010_debugger_gate", "debugger-fault")
fatal_gate = _load("art_w010_fatal_gate", "fatal-runtime")


def test_w010_uef_gate_accepts_one_handled_and_three_fatal_modes(
    tmp_path, monkeypatch
):
    probe = tmp_path / "win32_uef_probe.exe"
    probe.write_bytes(b"probe")
    outputs = {
        "seh": (0, "WIN32_UEF_PROBE VEH enter code=0xc0000005\nWIN32_UEF_PROBE PASS seh"),
        "unhandled": (
            0xC0000005,
            "WIN32_UEF_PROBE main armed=1\n"
            "WIN32_UEF_PROBE VEH enter code=0xc0000005\n"
            "WIN32_UEF_PROBE UEF first code=0xc0000005",
        ),
        "chain": (
            0xC0000005,
            "WIN32_UEF_PROBE UEF second chaining=1\n"
            "WIN32_UEF_PROBE UEF first code=0xc0000005",
        ),
        "thread": (
            0xC0000005,
            "WIN32_UEF_PROBE worker armed=1\n"
            "WIN32_UEF_PROBE VEH enter code=0xc0000005\n"
            "WIN32_UEF_PROBE UEF first code=0xc0000005",
        ),
    }

    def run(command, **kwargs):
        code, output = outputs[command[-1]]
        return SimpleNamespace(returncode=code, stdout=output, stderr="")

    monkeypatch.setattr(uef_gate.subprocess, "run", run)
    work = tmp_path / "out" / "uef"
    uef_gate.run_gate(
        target_id="windows-x86_64-msvc",
        probe=probe,
        work_root=work,
        timeout=30,
    )
    record_text = (work / "result.json").read_text(encoding="utf-8")
    assert json.loads(record_text)["completed_cases"] == 4
    assert str(tmp_path) not in record_text


def test_w010_managed_fault_gate_runs_six_cases_without_dumps(tmp_path, monkeypatch):
    calls = []

    def run_managed(**kwargs):
        calls.append(kwargs)
        (kwargs["work_root"] / "result.json").write_text(
            json.dumps({"target_id": kwargs["target_id"]}) + "\n", encoding="utf-8"
        )

    monkeypatch.setattr(managed_gate.runtime_gate, "run_managed", run_managed)
    work = tmp_path / "out" / "managed"
    managed_gate.run_gate(
        target_id="windows-x86_64-msvc",
        dalvikvm=tmp_path / "dalvikvm.exe",
        boot_jar=tmp_path / "boot.jar",
        app_jar=tmp_path / "app.jar",
        work_root=work,
        icu_data=tmp_path / "icudt.dat",
        library_dirs=[tmp_path],
        timeout=30,
    )
    assert len(calls) == 6
    assert calls[0]["require_nonzero"] is True
    assert all(call["main_class"] == "W010ManagedFaultProbe" for call in calls)
    assert json.loads((work / "result.json").read_text())["dump_files"] == []


def test_w010_debugger_gate_stages_regular_files_and_runs_both_modes(
    tmp_path, monkeypatch
):
    files = {}
    for name in ("debugger.exe", "dalvikvm.exe", "boot.jar", "app.jar", "icudt.dat"):
        path = tmp_path / name
        path.write_bytes(name.encode())
        files[name] = path
    outputs = {
        "npe": (
            "WIN32_DEBUGGER_PROBE first_chance_av stop=1 continue=DBG_EXCEPTION_NOT_HANDLED\n"
            "WIN32_DEBUGGER_PROBE result mode=npe child_exit=0 first_stack_overflow=0\n"
            "WIN32_DEBUGGER_PROBE PASS mode=npe\n"
            "W010ManagedFaultProbe NPE OK read=64 write=64 recovery=128 gc=16"
        ),
        "so": (
            "WIN32_DEBUGGER_PROBE result mode=so child_exit=0 first_av=0 "
            "first_stack_overflow=0 first_hardware=0\n"
            "WIN32_DEBUGGER_PROBE PASS mode=so\n"
            "W010ManagedFaultProbe SO OK main=2 child=2 recovery=4 gc=4"
        ),
    }

    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout=outputs[command[-1]], stderr="")

    monkeypatch.setattr(debugger_gate.subprocess, "run", run)
    work = tmp_path / "out" / "debugger"
    debugger_gate.run_gate(
        target_id="windows-x86_64-msvc",
        probe=files["debugger.exe"],
        dalvikvm=files["dalvikvm.exe"],
        boot_jar=files["boot.jar"],
        app_jar=files["app.jar"],
        work_root=work,
        icu_data=files["icudt.dat"],
        library_dirs=[tmp_path],
        timeout=30,
    )
    record_text = (work / "result.json").read_text(encoding="utf-8")
    assert json.loads(record_text)["completed_cases"] == 2
    assert str(tmp_path) not in record_text
    assert all(command[1] == str(files["dalvikvm.exe"]) for command in commands)
    assert not (work / "dalvikvm.exe").exists()


def test_w010_fatal_gate_requires_three_valid_native_dumps(tmp_path, monkeypatch):
    calls = []

    def run_managed(**kwargs):
        calls.append(kwargs)
        work = kwargs["work_root"]
        (work / "result.json").write_text(
            json.dumps({"target_id": kwargs["target_id"]}) + "\n", encoding="utf-8"
        )
        if kwargs["main_class"] == "CrashNativeProbe":
            dump = work / "run" / "crash" / "fatal.dmp"
            dump.write_bytes(b"MDMP" + b"x" * 4097)

    monkeypatch.setattr(fatal_gate.runtime_gate, "run_managed", run_managed)
    common = dict(
        target_id="windows-x86_64-msvc",
        dalvikvm=tmp_path / "dalvikvm.exe",
        boot_jar=tmp_path / "boot.jar",
        app_jar=tmp_path / "app.jar",
        icu_data=tmp_path / "icudt.dat",
        library_dirs=[tmp_path],
        timeout=30,
    )
    fatal_gate.run_gate(mode="abort", work_root=tmp_path / "abort", **common)
    fatal_gate.run_gate(mode="native", work_root=tmp_path / "native", **common)
    assert len(calls) == 4
    assert all(call["require_nonzero"] for call in calls)
    native = json.loads((tmp_path / "native" / "result.json").read_text())
    assert native["completed_cases"] == 3
    assert native["dump_count"] == 3
