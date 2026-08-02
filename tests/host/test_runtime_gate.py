from pathlib import Path
import importlib.util
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest


_RUNTIME_GATE_PATH = Path(__file__).parents[1] / "support" / "runtime_gate.py"
_SPEC = importlib.util.spec_from_file_location("art_runtime_gate", _RUNTIME_GATE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
runtime_gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(runtime_gate)

_FS1_GATE_PATH = (
    Path(__file__).parents[1]
    / "support"
    / "windows"
    / "fs1_stack_high_water_gate.py"
)
_FS1_SPEC = importlib.util.spec_from_file_location("art_fs1_gate", _FS1_GATE_PATH)
assert _FS1_SPEC is not None and _FS1_SPEC.loader is not None
fs1_gate = importlib.util.module_from_spec(_FS1_SPEC)
_FS1_SPEC.loader.exec_module(fs1_gate)

_W002_GATE_PATH = (
    Path(__file__).parents[1]
    / "support"
    / "windows"
    / "w002_managed_entry_gate.py"
)
_W002_SPEC = importlib.util.spec_from_file_location("art_w002_gate", _W002_GATE_PATH)
assert _W002_SPEC is not None and _W002_SPEC.loader is not None
w002_gate = importlib.util.module_from_spec(_W002_SPEC)
_W002_SPEC.loader.exec_module(w002_gate)

_W003_GATE_PATH = (
    Path(__file__).parents[1]
    / "support"
    / "w003_managed_gate.py"
)
_W003_SPEC = importlib.util.spec_from_file_location("art_w003_gate", _W003_GATE_PATH)
assert _W003_SPEC is not None and _W003_SPEC.loader is not None
w003_gate = importlib.util.module_from_spec(_W003_SPEC)
_W003_SPEC.loader.exec_module(w003_gate)

_JVMTI_GATE_PATH = Path(__file__).parents[1] / "cases" / "jvmti-force" / "run.py"
_JVMTI_SPEC = importlib.util.spec_from_file_location("art_jvmti_gate", _JVMTI_GATE_PATH)
assert _JVMTI_SPEC is not None and _JVMTI_SPEC.loader is not None
jvmti_gate = importlib.util.module_from_spec(_JVMTI_SPEC)
_JVMTI_SPEC.loader.exec_module(jvmti_gate)


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


def test_native_gate_repeats_without_shell_and_records_sanitized_result(
    tmp_path, monkeypatch, capsys
):
    probe = tmp_path / "probe.exe"
    probe.write_bytes(b"native probe")
    commands = []

    def run(command, **kwargs):
        commands.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout="probe count=1 failures=0\nprobe OK\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", run)
    work = tmp_path / "out" / "tests" / "results" / "native"
    runtime_gate.run_native(
        target_id="windows-x86_64-msvc",
        probe=probe,
        work_root=work,
        library_dirs=[tmp_path],
        probe_args=["success"],
        expected=["probe count=1 failures=0", "probe OK"],
        forbidden=["probe FAIL"],
        expected_exit=0,
        repetitions=3,
        timeout=5,
    )

    assert len(commands) == 3
    for command, options in commands:
        assert command == [str(probe), "success"]
        assert options["cwd"] == probe.parent
        assert options["shell"] is False
        assert options["timeout"] == 5
    record_text = (work / "result.json").read_text(encoding="utf-8")
    record = json.loads(record_text)
    assert record["requested_repetitions"] == 3
    assert record["completed_repetitions"] == 3
    assert all(case["actual_exit"] == 0 for case in record["cases"])
    assert str(tmp_path) not in record_text
    assert "repetitions=3" in capsys.readouterr().out


def test_native_matrix_runs_named_cases_and_records_sanitized_result(
    tmp_path, monkeypatch, capsys
):
    probe = tmp_path / "probe.exe"
    probe.write_bytes(b"native probe")
    matrix = tmp_path / "runtime-matrix.json"
    matrix.write_text(
        json.dumps({
            "schema_version": 1,
            "cases": [
                {
                    "name": "first",
                    "arguments": ["first"],
                    "expected_markers": ["probe first OK"],
                    "repetitions": 2,
                    "timeout_seconds": 7,
                },
                {
                    "name": "second",
                    "arguments": ["second"],
                    "expected_markers": ["probe second OK"],
                },
            ],
        }),
        encoding="utf-8",
    )
    commands = []

    def run(command, **kwargs):
        commands.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=f"probe {command[-1]} OK\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", run)
    work = tmp_path / "out" / "results" / "matrix"
    runtime_gate.run_native_matrix(
        target_id="windows-x86_64-msvc",
        probe=probe,
        work_root=work,
        library_dirs=[tmp_path],
        matrix=matrix,
    )

    assert [command for command, _ in commands] == [
        [str(probe), "first"],
        [str(probe), "first"],
        [str(probe), "second"],
    ]
    assert all(options["shell"] is False for _, options in commands)
    record_text = (work / "result.json").read_text(encoding="utf-8")
    record = json.loads(record_text)
    assert record["requested_cases"] == 2
    assert record["completed_cases"] == 2
    assert record["matrix"]["name"] == matrix.name
    assert str(tmp_path) not in record_text
    assert "cases=2, repetitions=3" in capsys.readouterr().out


def test_fs1_gate_runs_three_managed_modes_and_validator_without_shell(
    tmp_path, monkeypatch, capsys
):
    files = {}
    for name in ("dalvikvm.exe", "boot.jar", "probe.jar", "icudt72l.dat", "check.py"):
        path = tmp_path / name
        path.write_bytes(name.encode())
        files[name] = path
    jni_dir = tmp_path / "jni"
    jni_dir.mkdir()
    calls = []

    def run_managed(**kwargs):
        calls.append(kwargs)
        case_root = kwargs["work_root"]
        case_root.mkdir(parents=True)
        (case_root / "stdout.txt").write_text(
            f"FS1StackHighWaterProbe OK mode={kwargs['main_args'][0]} main=2 child=2\n",
            encoding="utf-8",
        )
        (case_root / "stderr.txt").write_text("", encoding="utf-8")
        (case_root / "result.json").write_text(
            json.dumps({"target_id": kwargs["target_id"]}) + "\n",
            encoding="utf-8",
        )

    validator_calls = []

    def validate(command, **kwargs):
        validator_calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="validation PASS\n", stderr="")

    monkeypatch.setattr(fs1_gate.runtime_gate, "run_managed", run_managed)
    monkeypatch.setattr(fs1_gate.subprocess, "run", validate)
    work = tmp_path / "out" / "fs1"
    fs1_gate.run_gate(
        target_id="windows-x86_64-msvc",
        dalvikvm=files["dalvikvm.exe"],
        boot_jar=files["boot.jar"],
        app_jar=files["probe.jar"],
        work_root=work,
        icu_data=files["icudt72l.dat"],
        jni_dir=jni_dir,
        library_dirs=[tmp_path],
        validator=files["check.py"],
        art_reserve=8192,
        timeout=30,
    )

    assert [call["main_args"] for call in calls] == [
        ["switch"],
        ["nterp"],
        ["jit"],
    ]
    assert calls[0]["environment_overrides"]["ART_WINDOWS_X64_NTERP"] == "0"
    assert calls[1]["environment_overrides"]["ART_WINDOWS_X64_NTERP"] == "1"
    assert calls[2]["environment_overrides"]["ART_WINDOWS_X64_JIT"] == "1"
    assert all(options["shell"] is False for _, options in validator_calls)
    record_text = (work / "result.json").read_text(encoding="utf-8")
    record = json.loads(record_text)
    assert record["completed_modes"] == 3
    assert record["dump_files"] == []
    assert str(tmp_path) not in record_text
    assert "modes=3, art_reserve=8192, dumps=0" in capsys.readouterr().out


def test_w003_frame_gate_runs_four_modes_twice_and_records_sanitized_result(
    tmp_path, monkeypatch, capsys
):
    files = {}
    for name in ("dalvikvm.exe", "boot.jar", "probe.jar", "probe.dll", "icudt.dat"):
        path = tmp_path / name
        path.write_bytes(name.encode())
        files[name] = path
    calls = []

    def run_managed(**kwargs):
        calls.append(kwargs)
        case_root = kwargs["work_root"]
        mode = next(
            option.split("=", 1)[1]
            for option in kwargs["vm_options"]
            if option.startswith("-Dw003.mode=")
        )
        lines = []
        for phase in ("refs_only", "refs_and_args", "all_callee_saves", "everything"):
            lines.append(
                f"W003FrameProbe mode={mode} phase={phase} "
                "counts=refs_only:1,refs_and_args:1,"
                "all_callee_saves:1,everything:1 checksum=1"
            )
        lines.append(f"W003FrameProbe OK mode={mode} checksum=1")
        (case_root / "stdout.txt").write_text("\n".join(lines), encoding="utf-8")
        (case_root / "stderr.txt").write_text("", encoding="utf-8")
        (case_root / "result.json").write_text(
            json.dumps({"target_id": kwargs["target_id"]}) + "\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(w003_gate.runtime_gate, "run_managed", run_managed)
    work = tmp_path / "out" / "w003-frame"
    w003_gate.run_gate(
        case="frame",
        target_id="windows-x86_64-msvc",
        dalvikvm=files["dalvikvm.exe"],
        boot_jar=files["boot.jar"],
        app_jar=files["probe.jar"],
        probe=files["probe.dll"],
        work_root=work,
        icu_data=files["icudt.dat"],
        library_dirs=[tmp_path],
        repetitions=2,
        timeout=10,
    )

    assert len(calls) == 8
    assert [call["environment_overrides"]["ART_WINDOWS_X64_NTERP"] for call in calls] == [
        "0",
        "0",
        "0",
        "0",
        "1",
        "1",
        "1",
        "1",
    ]
    result_text = (work / "result.json").read_text(encoding="utf-8")
    result = json.loads(result_text)
    assert result["completed_runs"] == 8
    assert result["dump_files"] == []
    assert str(tmp_path) not in result_text
    assert "repetitions=2, runs=8, dumps=0" in capsys.readouterr().out


def test_w003_jni_abi_targets_are_exact_and_host_independent():
    assert w003_gate._target_platform("linux-x86_64-gnu") == "linux"
    assert w003_gate._target_platform("windows-x86_64-msvc") == "windows"
    assert w003_gate._target_jit_options("linux") == [
        "-verbose:jit",
        "-Xjitwarmupthreshold:0",
        "-Xjitthreshold:0",
    ]
    assert w003_gate._target_jit_options("windows") == ["-Xjitthreshold:0"]
    assert w003_gate._target_jit_environment("linux", "Probe") == {}
    assert w003_gate._target_jit_environment("windows", "Probe") == {
        "ART_WINDOWS_X64_JIT": "1",
        "ART_WINDOWS_X64_NTERP": "1",
        "ART_WINDOWS_X64_JIT_FILTER": "Probe",
        "ART_WINDOWS_X64_JIT_LOG_COMPILES": "1",
    }
    with pytest.raises(w003_gate.runtime_gate.GateError, match="no accepted runner"):
        w003_gate._target_platform("windows-aarch64-msvc")


def test_jvmti_force_gate_repeats_and_records_sanitized_result(
    tmp_path, monkeypatch, capsys
):
    files = {}
    for name in (
        "dalvikvm.exe",
        "boot.jar",
        "probe.jar",
        "agent.dll",
        "plugin.dll",
        "icudt.dat",
    ):
        path = tmp_path / name
        path.write_bytes(name.encode())
        files[name] = path
    calls = []

    def run_managed(**kwargs):
        calls.append(kwargs)
        case_root = kwargs["work_root"]
        output = [
            f"JvmtiForceProbe {phase} {jvmti_gate._VALUES}"
            for phase in ("before", "during", "after")
        ]
        output.extend(
            [
                "JvmtiForceProbe steps before=0 during=20 disabled=25 final=25",
                "success=1 method=double JvmtiForceProbe.normalRegistered(",
                "success=1 method=double JvmtiForceProbe.fastRegistered(",
                "JvmtiForceProbe OK",
                "main end exception=0",
            ]
        )
        (case_root / "stdout.txt").write_text("\n".join(output), encoding="utf-8")
        (case_root / "stderr.txt").write_text("", encoding="utf-8")
        (case_root / "result.json").write_text(
            json.dumps({"target_id": kwargs["target_id"]}) + "\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(jvmti_gate.runtime_gate, "run_managed", run_managed)
    work = tmp_path / "out" / "jvmti-force"
    jvmti_gate.run_gate(
        target_id="windows-x86_64-msvc",
        dalvikvm=files["dalvikvm.exe"],
        boot_jar=files["boot.jar"],
        app_jar=files["probe.jar"],
        agent=files["agent.dll"],
        plugin=files["plugin.dll"],
        work_root=work,
        icu_data=files["icudt.dat"],
        library_dirs=[tmp_path],
        repetitions=3,
        timeout=30,
    )

    assert len(calls) == 3
    assert all("-Xplugin:openjdkjvmti.dll" in call["vm_options"] for call in calls)
    assert all(
        call["environment_overrides"]["ART_WINDOWS_X64_JIT_FILTER"]
        == "JvmtiForceProbe"
        for call in calls
    )
    assert all(
        (call["work_root"] / "libjvmtiforceprobe.dll").is_file()
        for call in calls
    )
    result_text = (work / "result.json").read_text(encoding="utf-8")
    result = json.loads(result_text)
    assert result["completed_runs"] == 3
    assert result["dump_files"] == []
    assert str(tmp_path) not in result_text
    assert "runs=3, compiled_targets=2, dumps=0" in capsys.readouterr().out


def test_w002_contract_keeps_osr_return_path_mode_specific():
    _, _, nterp_expected, nterp_environment, nterp_forbidden = (
        w002_gate._case_contract("osr", "nterp", None)
    )
    _, _, switch_expected, switch_environment, switch_forbidden = (
        w002_gate._case_contract("osr", "switch", None)
    )
    completion = "Done running OSR code for long W002OsrProbe.osrLoop(int)"
    assert completion in nterp_forbidden
    assert completion not in nterp_expected
    assert completion in switch_expected
    assert completion not in switch_forbidden
    assert nterp_environment["ART_WINDOWS_X64_NTERP"] == "1"
    assert switch_environment["ART_WINDOWS_X64_NTERP"] == "0"


def test_w002_attach_gate_runs_two_modes_and_sanitizes_results(
    tmp_path, monkeypatch, capsys
):
    files = {}
    for name in ("dalvikvm.exe", "boot.jar", "attach.jar", "icudt72l.dat"):
        path = tmp_path / name
        path.write_bytes(name.encode())
        files[name] = path
    jni_dir = tmp_path / "jni"
    jni_dir.mkdir()
    calls = []

    def run_managed(**kwargs):
        calls.append(kwargs)
        case_root = kwargs["work_root"]
        case_root.mkdir(parents=True)
        (case_root / "result.json").write_text(
            json.dumps({"target_id": kwargs["target_id"]}) + "\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(w002_gate.runtime_gate, "run_managed", run_managed)
    work = tmp_path / "out" / "w002"
    w002_gate.run_gate(
        case="attach",
        target_id="windows-x86_64-msvc",
        dalvikvm=files["dalvikvm.exe"],
        boot_jar=files["boot.jar"],
        app_jar=files["attach.jar"],
        work_root=work,
        icu_data=files["icudt72l.dat"],
        jni_dir=jni_dir,
        library_dirs=[tmp_path],
        repetitions=2,
        timeout=30,
    )

    assert len(calls) == 4
    assert [call["environment_overrides"]["ART_WINDOWS_X64_NTERP"] for call in calls] == [
        "1",
        "1",
        "0",
        "0",
    ]
    assert all("-Xjitthreshold:0" in call["vm_options"] for call in calls)
    record_text = (work / "result.json").read_text(encoding="utf-8")
    record = json.loads(record_text)
    assert record["completed_runs"] == 4
    assert record["dump_files"] == []
    assert str(tmp_path) not in record_text
    assert "modes=2, repetitions=2, runs=4, dumps=0" in capsys.readouterr().out


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
    cacerts = tmp_path / "cacerts"
    cacerts.mkdir()
    (cacerts / "01234567.0").write_text("certificate\n", encoding="utf-8")
    properties = tmp_path / "security.properties"
    properties.write_text("keystore.type=AndroidCAStore\n", encoding="utf-8")
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
        environment_overrides={"ART_TEST_MODE": "switch"},
        cacerts_dir=cacerts,
        security_properties=properties,
    )

    command, options = commands[0]
    assert command[0] == str(dalvikvm)
    assert "-Xint" in command
    assert options["shell"] is False
    assert options["env"]["ANDROID_ROOT"] == str(work / "runtime")
    assert options["env"]["ART_TEST_MODE"] == "switch"
    assert (work / "runtime" / "icu" / "icudt72l.dat").read_bytes() == b"icu"
    assert (
        work / "runtime" / "etc" / "security" / "cacerts" / "01234567.0"
    ).is_file()
    assert (
        work / "runtime" / "data" / "misc" / "keychain" / "cacerts-added"
    ).is_dir()
    result = (work / "result.json").read_text(encoding="utf-8")
    assert '"target_id": "linux-x86_64-gnu"' in result
    assert str(tmp_path) not in result
    assert '"count": 1' in result
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


def test_managed_gate_accepts_declared_nonzero_fatal_exit(tmp_path, monkeypatch):
    files = []
    for name in ("dalvikvm.exe", "boot.jar", "fatal.jar", "icudt.dat"):
        path = tmp_path / name
        path.write_bytes(name.encode())
        files.append(path)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: SimpleNamespace(
            returncode=0xC0000005,
            stdout="fatal marker\n",
            stderr="minidump written\n",
        ),
    )
    work = tmp_path / "work"
    runtime_gate.run_managed(
        target_id="windows-x86_64-msvc",
        dalvikvm=files[0],
        boot_jar=files[1],
        app_jar=files[2],
        main_class="FatalProbe",
        work_root=work,
        icu_data=files[3],
        library_dirs=[tmp_path],
        vm_options=[],
        main_args=[],
        expected=["fatal marker", "minidump written"],
        forbidden=["unexpected return"],
        expected_exit=0,
        timeout=30,
        require_nonzero=True,
    )
    result = json.loads((work / "result.json").read_text(encoding="utf-8"))
    assert result["exit_contract"] == "nonzero"
    assert result["expected_exit"] is None
    assert result["actual_exit"] == 0xC0000005
