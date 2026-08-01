from pathlib import Path
import importlib.util
import json


_RUNNER = (
    Path(__file__).parents[1] / "cases" / "jit-runtime-controls" / "run.py"
)
_SPEC = importlib.util.spec_from_file_location("jit_runtime_controls", _RUNNER)
assert _SPEC is not None and _SPEC.loader is not None
runner = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(runner)


def test_jit_runtime_controls_are_shell_free_and_portable(tmp_path, monkeypatch):
    files = {}
    for name in (
        "dalvikvm.exe",
        "boot.jar",
        "hello.jar",
        "math.jar",
        "io.jar",
        "net.jar",
        "gc.jar",
        "throw.jar",
        "icudt72l.dat",
    ):
        path = tmp_path / name
        path.write_bytes(name.encode())
        files[name] = path

    calls = []

    def run_managed(**kwargs):
        calls.append(kwargs)
        root = kwargs["work_root"]
        (root / "runtime" / "tmp").mkdir(parents=True)
        environment = kwargs["environment_overrides"]
        compile_lines = []
        if (
            environment["ART_WINDOWS_X64_JIT_LOG_COMPILES"] == "1"
            and environment["ART_WINDOWS_X64_JIT"] != "0"
            and "-Xusejit:false" not in kwargs["vm_options"]
        ):
            filter_value = environment["ART_WINDOWS_X64_JIT_FILTER"]
            exclude_value = environment["ART_WINDOWS_X64_JIT_EXCLUDE"]
            if filter_value:
                compile_lines.append(runner._COMPILE_MARKER + filter_value)
            elif exclude_value:
                compile_lines.append(runner._COMPILE_MARKER + "java.lang.StringFactory")
            else:
                compile_lines.extend([
                    runner._COMPILE_MARKER + "java.lang.StringBuilder",
                    runner._COMPILE_MARKER
                    + "java.lang.String java.lang.StringFactory.newStringFromBytes",
                ])
        (root / "stdout.txt").write_text("\n".join(compile_lines), encoding="utf-8")
        (root / "stderr.txt").write_text("", encoding="utf-8")
        (root / "result.json").write_text(
            json.dumps({"target_id": kwargs["target_id"]}) + "\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(runner.runtime_gate, "run_managed", run_managed)
    work = tmp_path / "out" / "jit-controls"
    runner.run_gate(
        target_id="windows-x86_64-msvc",
        dalvikvm=files["dalvikvm.exe"],
        boot_jar=files["boot.jar"],
        hello_jar=files["hello.jar"],
        math_jar=files["math.jar"],
        io_jar=files["io.jar"],
        net_jar=files["net.jar"],
        gc_jar=files["gc.jar"],
        throw_jar=files["throw.jar"],
        work_root=work,
        icu_data=files["icudt72l.dat"],
        library_dirs=[tmp_path],
        timeout=30,
    )
    assert len(calls) == 12
    assert sum(call["require_nonzero"] for call in calls) == 1
    assert all(call["target_id"] == "windows-x86_64-msvc" for call in calls)
    record_text = (work / "result.json").read_text(encoding="utf-8")
    assert json.loads(record_text)["completed_cases"] == 12
    assert str(tmp_path) not in record_text
