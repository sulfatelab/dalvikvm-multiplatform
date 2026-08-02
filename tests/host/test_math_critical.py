from pathlib import Path
import importlib.util
import json


_RUNNER = Path(__file__).parents[1] / "cases" / "math-critical" / "run.py"
_SPEC = importlib.util.spec_from_file_location("math_critical_gate", _RUNNER)
assert _SPEC is not None and _SPEC.loader is not None
runner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(runner)


def test_math_critical_runs_xint_and_jit_without_shell(tmp_path, monkeypatch):
    files = {}
    for name in (
        "dalvikvm.exe",
        "boot.jar",
        "math.jar",
        "icudt72l.dat",
        "target-runner",
    ):
        path = tmp_path / name
        path.write_bytes(name.encode())
        files[name] = path
    calls = []

    def run_managed(**kwargs):
        calls.append(kwargs)
        root = kwargs["work_root"]
        (root / "runtime" / "tmp").mkdir(parents=True)
        compile_line = ""
        if "-Xjitthreshold:0" in kwargs["vm_options"]:
            compile_line = runner._COMPILE_MARKER + "void MathCriticalProbe.main"
        (root / "stdout.txt").write_text(compile_line, encoding="utf-8")
        (root / "stderr.txt").write_text("", encoding="utf-8")
        (root / "result.json").write_text(
            json.dumps({"target_id": kwargs["target_id"]}) + "\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(runner.runtime_gate, "run_managed", run_managed)
    work = tmp_path / "out" / "math"
    runner.run_gate(
        target_id="windows-x86_64-msvc",
        dalvikvm=files["dalvikvm.exe"],
        boot_jar=files["boot.jar"],
        app_jar=files["math.jar"],
        work_root=work,
        icu_data=files["icudt72l.dat"],
        library_dirs=[tmp_path],
        repetitions=2,
        timeout=30,
        runner=files["target-runner"],
        runner_args=["-L", "target-root"],
    )
    assert len(calls) == 4
    assert sum("-Xint" in call["vm_options"] for call in calls) == 2
    assert sum("-Xjitthreshold:0" in call["vm_options"] for call in calls) == 2
    assert all(call["main_class"] == "MathCriticalProbe" for call in calls)
    assert all(call["runner"] == files["target-runner"] for call in calls)
    assert all(call["runner_args"] == ["-L", "target-root"] for call in calls)
    record_text = (work / "result.json").read_text(encoding="utf-8")
    assert json.loads(record_text)["completed_cases"] == 4
    assert str(tmp_path) not in record_text
