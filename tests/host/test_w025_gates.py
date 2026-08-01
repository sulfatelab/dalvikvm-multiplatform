from pathlib import Path
import importlib.util
import json
from types import SimpleNamespace


CASES_ROOT = Path(__file__).parents[1] / "cases"
REVIEWER = Path(__file__).parents[1] / "support" / "windows" / "check_w025_jit_contract.py"
REPO_ROOT = Path(__file__).parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


unwind_gate = _load(
    "art_w025_unwind_gate",
    CASES_ROOT / "jit-unwind-lifecycle" / "run.py",
)
stress_gate = _load(
    "art_w025_stress_gate",
    CASES_ROOT / "jit-lifecycle-stress" / "run.py",
)
mapping_gate = _load(
    "art_w025_mapping_gate",
    CASES_ROOT / "jit-mapping" / "run.py",
)
policy_gate = _load(
    "art_w025_policy_gate",
    CASES_ROOT / "jit-section-policy" / "run.py",
)
reviewer = _load("art_w025_reviewer", REVIEWER)


def _fake_managed_run(**kwargs):
    work = kwargs["work_root"]
    (work / "runtime" / "tmp").mkdir(parents=True, exist_ok=True)
    output = "Total number of JIT code cache collections: 1\n"
    (work / "stdout.txt").write_text(output, encoding="utf-8")
    (work / "stderr.txt").write_text("", encoding="utf-8")
    (work / "result.json").write_text(
        json.dumps({"target_id": kwargs["target_id"]}) + "\n",
        encoding="utf-8",
    )


def _managed_inputs(tmp_path: Path) -> dict[str, Path]:
    inputs = {}
    for name in ("probe.dll", "dalvikvm.exe", "boot.jar", "app.jar", "icudt72l.dat"):
        path = tmp_path / name
        path.write_bytes(name.encode())
        inputs[name] = path
    return inputs


def test_w025_managed_runners_stage_both_dso_names_and_sanitize_results(
    tmp_path, monkeypatch
):
    files = _managed_inputs(tmp_path)
    common = dict(
        target_id="windows-x86_64-msvc",
        probe=files["probe.dll"],
        dalvikvm=files["dalvikvm.exe"],
        boot_jar=files["boot.jar"],
        app_jar=files["app.jar"],
        icu_data=files["icudt72l.dat"],
        library_dirs=[tmp_path],
        timeout=30,
    )

    monkeypatch.setattr(unwind_gate.runtime_gate, "run_managed", _fake_managed_run)
    unwind_work = tmp_path / "out" / "unwind"
    unwind_gate.run_gate(work_root=unwind_work, **common)
    assert (unwind_work / "libjitunwindlifecycleprobe.dll").is_file()
    assert (unwind_work / "jitunwindlifecycleprobe.dll").is_file()

    monkeypatch.setattr(stress_gate.runtime_gate, "run_managed", _fake_managed_run)
    stress_work = tmp_path / "out" / "stress"
    stress_gate.run_gate(work_root=stress_work, **common)
    assert (stress_work / "libw025jitlifecyclestressprobe.dll").is_file()
    assert (stress_work / "w025jitlifecyclestressprobe.dll").is_file()

    monkeypatch.setattr(mapping_gate.runtime_gate, "run_managed", _fake_managed_run)
    mapping_work = tmp_path / "out" / "mapping"
    mapping_gate.run_gate(work_root=mapping_work, **common)
    record_text = (mapping_work / "result.json").read_text(encoding="utf-8")
    assert json.loads(record_text)["completed_cases"] == 2
    assert str(tmp_path) not in record_text
    for capacity in (64, 1024):
        case = mapping_work / f"capacity-{capacity}m"
        assert (case / "libw025jitmappingprobe.dll").is_file()
        assert (case / "w025jitmappingprobe.dll").is_file()


def test_w025_policy_gate_runs_four_shell_free_cases_with_original_dalvikvm(
    tmp_path, monkeypatch
):
    files = {}
    for name in (
        "launcher.exe",
        "section.exe",
        "mapping.dll",
        "dalvikvm.exe",
        "boot.jar",
        "mapping.jar",
        "hello.jar",
        "icudt72l.dat",
    ):
        path = tmp_path / name
        path.write_bytes(name.encode())
        files[name] = path

    commands = []

    def run(command, **kwargs):
        commands.append((command, kwargs))
        if command[1] == "cfg" and "W025JitMappingProbe" not in command:
            output = (
                "W025_POLICY_CHILD policy=cfg cfg_enabled=1\n"
                "W025_SECTION_MAPPING label=default execute=1\n"
                "W025_SECTION_POLICY_PASS mode=cfg-call\n"
                "W025_POLICY_LAUNCHER_PASS policy=cfg child_exit=0 expected=zero\n"
            )
        elif command[1] == "cfg":
            output = (
                "W025_POLICY_CHILD policy=cfg cfg_enabled=1\n"
                "Windows x64 JIT dual-view (J-2) created: capacity=64MiB\n"
                "W025_JIT_MAPPING_PASS\n"
                "success=1 method=int W025JitMappingProbe.target(int)\n"
                "W025JitMappingProbe PASS capacity_bytes=67108864 require_cfg=true\n"
                "W025_POLICY_LAUNCHER_PASS policy=cfg child_exit=0 expected=zero\n"
            )
        elif "-Xusejit:false" in command:
            output = (
                "W025_POLICY_CHILD policy=dynamic dynamic_prohibit=1\n"
                "Hello from dalvikvm!\nmain end exception=0\n"
                "W025_POLICY_LAUNCHER_PASS policy=dynamic child_exit=0 expected=zero\n"
            )
        else:
            output = (
                "W025_POLICY_CHILD policy=dynamic dynamic_prohibit=1\n"
                "Windows x64 JIT dual-view construction failed: failed: 1655\n"
                "Failed to create JIT Code Cache:\n"
                "Hello from dalvikvm!\nmain end exception=0\n"
                "W025_POLICY_LAUNCHER_PASS policy=dynamic child_exit=0 expected=zero\n"
            )
        return SimpleNamespace(returncode=0, stdout=output, stderr="")

    monkeypatch.setattr(policy_gate.subprocess, "run", run)
    work = tmp_path / "out" / "policy"
    policy_gate.run_gate(
        target_id="windows-x86_64-msvc",
        launcher=files["launcher.exe"],
        section_probe=files["section.exe"],
        mapping_probe=files["mapping.dll"],
        dalvikvm=files["dalvikvm.exe"],
        boot_jar=files["boot.jar"],
        mapping_jar=files["mapping.jar"],
        hello_jar=files["hello.jar"],
        work_root=work,
        icu_data=files["icudt72l.dat"],
        library_dirs=[tmp_path],
        timeout=30,
    )
    assert len(commands) == 4
    assert all(options["shell"] is False for _, options in commands)
    assert all(command[3] == str(files["dalvikvm.exe"]) for command, _ in commands[1:])
    record_text = (work / "result.json").read_text(encoding="utf-8")
    record = json.loads(record_text)
    assert record["completed_cases"] == 4
    assert record["reparse_paths"] == []
    assert str(tmp_path) not in record_text


def test_w025_reviewer_matches_current_source_and_writes_portable_json(
    tmp_path, monkeypatch
):
    assert reviewer.check_source_policy(REPO_ROOT) == {
        "pagefile_section_implementations": 1,
        "managed_methods": 16,
        "jni_methods": 8,
        "nterp_xmm0_return_forms": 2,
        "windows_jit_memory_paths": 1,
        "pe_jit_inspection_exports": 2,
    }
    artifacts = {}
    for name in ("art.dll", "section.exe", "stress.dll"):
        path = tmp_path / name
        path.write_bytes(name.encode())
        artifacts[name] = path
    monkeypatch.setattr(
        reviewer,
        "check_source_policy",
        lambda repo: {"managed_methods": 16, "jni_methods": 8},
    )
    monkeypatch.setattr(
        reviewer,
        "check_pe_policy",
        lambda **kwargs: {"cfg_flags": 2, "jni_exports": 9},
    )
    monkeypatch.setattr(
        reviewer,
        "check_art_binary",
        lambda art: {"required_markers": 3, "retired_markers": 0},
    )
    result = tmp_path / "out" / "result.json"
    reviewer.run_review(
        target_id="windows-x86_64-msvc",
        repo=REPO_ROOT,
        art=artifacts["art.dll"],
        section_probe=artifacts["section.exe"],
        stress_probe=artifacts["stress.dll"],
        llvm_readobj=tmp_path / "llvm-readobj",
        result=result,
    )
    text = result.read_text(encoding="utf-8")
    assert json.loads(text)["status"] == "PASS"
    assert str(tmp_path) not in text
