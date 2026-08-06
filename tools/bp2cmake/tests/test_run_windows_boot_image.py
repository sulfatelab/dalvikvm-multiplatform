import argparse
import json
from pathlib import Path
import subprocess

import pytest

from tools import run_windows_boot_image
from tools import windows_aot_identity


def _args(tmp_path: Path) -> argparse.Namespace:
    dalvikvm = tmp_path / "bin" / "dalvikvm.exe"
    boot_jar = tmp_path / "inputs" / "boot.jar"
    app_jar = tmp_path / "inputs" / "hello.jar"
    icu_data = tmp_path / "inputs" / "icudt72l.dat"
    for path, data in (
        (dalvikvm, b"vm"),
        (boot_jar, b"boot"),
        (app_jar, b"hello"),
        (icu_data, b"icu"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    image_root = tmp_path / "generated" / "boot-image"
    image_dir = image_root / "x86_64"
    image_dir.mkdir(parents=True)
    artifacts = []
    for name in ("boot.art", "boot.oat", "boot.vdex"):
        path = image_dir / name
        path.write_bytes(name.encode())
        artifacts.append(
            {
                "path": f"x86_64/{name}",
                "size": path.stat().st_size,
                "sha256": run_windows_boot_image._sha256(path),
            }
        )
    (image_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "target_id": "windows-x86_64-msvc",
                "instruction_set": "x86_64",
                "logical_boot_jar": "/system/framework/boot.jar",
                "boot_jar_sha256": run_windows_boot_image._sha256(boot_jar),
                "image_base": "0x70000000",
                "image_format": "lz4",
                "compiler_filter": "speed",
                "compiler_parallelism": 1,
                "runtime_heap": {"initial": "64m", "maximum": "512m"},
                "generation_options": list(windows_aot_identity.generation_options()),
                "windows_aot_identity": windows_aot_identity.contract_record(),
                "artifacts": artifacts,
            }
        ),
        encoding="utf-8",
    )
    return argparse.Namespace(
        target_id="windows-x86_64-msvc",
        dalvikvm=dalvikvm,
        boot_jar=boot_jar,
        app_jar=app_jar,
        boot_image_dir=image_root,
        icu_data=icu_data,
        work_root=tmp_path / "out" / "w030",
        library_dir=[dalvikvm.parent],
        timeout=30,
    )


def test_launcher_stages_exact_package_identity_and_runs_once(tmp_path, monkeypatch):
    args = _args(tmp_path)
    calls = []

    def run(command, **options):
        calls.append((command, options))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Hello from dalvikvm!\nmain end exception=0\n",
            stderr="",
        )

    monkeypatch.setattr(run_windows_boot_image.subprocess, "run", run)
    output = run_windows_boot_image.run_gate(args)

    assert len(calls) == 1
    command, options = calls[0]
    assert "-Xbootclasspath:runtime/boot.jar" in command
    assert "-Xbootclasspath-locations:/system/framework/boot.jar" in command
    assert "-Ximage:runtime/boot-image/boot.art" in command
    assert options["cwd"] == output / "package"
    assert options["shell"] is False
    assert (output / "package" / "runtime" / "boot.jar").read_bytes() == b"boot"
    assert (
        output / "package" / "runtime" / "boot-image" / "x86_64" / "boot.oat"
    ).read_bytes() == b"boot.oat"
    result_text = (output / "result.json").read_text(encoding="utf-8")
    result = json.loads(result_text)
    assert len(result["launcher_rejected_mismatches"]) == 7
    assert result["working_directory"] == "package"
    assert str(tmp_path) not in result_text


def test_launcher_rejects_manifest_separator_drift_before_spawn(tmp_path, monkeypatch):
    args = _args(tmp_path)
    manifest_path = args.boot_image_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][0]["path"] = r"x86_64\boot.art"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        run_windows_boot_image.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("ART must not start"),
    )

    with pytest.raises(
        run_windows_boot_image.WindowsBootImageError,
        match="unexpected boot image artifact",
    ):
        run_windows_boot_image.run_gate(args)


def test_launcher_rejects_direct_mapped_windows_image_before_spawn(
    tmp_path, monkeypatch
):
    args = _args(tmp_path)
    manifest_path = args.boot_image_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["image_format"] = "uncompressed"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        run_windows_boot_image.subprocess,
        "run",
        lambda *_args, **_kwargs: pytest.fail("ART must not start"),
    )

    with pytest.raises(
        run_windows_boot_image.WindowsBootImageError,
        match="manifest does not match runtime inputs",
    ):
        run_windows_boot_image.run_gate(args)


def test_launcher_fails_if_art_falls_back_to_imageless(tmp_path, monkeypatch):
    args = _args(tmp_path)
    monkeypatch.setattr(
        run_windows_boot_image.subprocess,
        "run",
        lambda command, **options: subprocess.CompletedProcess(
            command,
            0,
            stdout="Hello from dalvikvm!\nmain end exception=0\n",
            stderr="Attempting to fall back to imageless running\n",
        ),
    )

    with pytest.raises(
        run_windows_boot_image.WindowsBootImageError,
        match="forbidden=.*imageless",
    ):
        run_windows_boot_image.run_gate(args)


def test_launcher_stages_native_probe_and_selects_aot_mode(tmp_path, monkeypatch):
    args = _args(tmp_path)
    probe = tmp_path / "inputs" / "w031probe.dll"
    probe.write_bytes(b"probe")
    args.main_class = "W031Probe"
    args.execution_mode = "aot"
    args.probe = probe
    args.probe_name = "w031probe"
    args.expect = ["W031 PASS", "main end exception=0"]
    args.forbid = ["W031 FAIL"]
    calls = []

    def run(command, **options):
        calls.append((command, options))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="W031 PASS\nmain end exception=0\n",
            stderr="",
        )

    monkeypatch.setattr(run_windows_boot_image.subprocess, "run", run)
    output = run_windows_boot_image.run_gate(args)

    command, _ = calls[0]
    assert "-Xusejit:false" in command
    assert "-Xint" not in command
    assert "-Djava.library.path=." in command
    assert command[-1] == "W031Probe"
    assert (output / "package" / "libw031probe.dll").read_bytes() == b"probe"
    assert (output / "package" / "w031probe.dll").read_bytes() == b"probe"
    record = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert record["main_class"] == "W031Probe"
    assert record["execution_mode"] == "aot"
