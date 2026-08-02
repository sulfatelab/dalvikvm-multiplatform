import argparse
import json
from pathlib import Path
import subprocess

import pytest

from tools import build_boot_image


def _args(tmp_path: Path) -> argparse.Namespace:
    dex2oat = tmp_path / "bin" / "dex2oat"
    boot_jar = tmp_path / "managed" / "boot.jar"
    dex2oat.parent.mkdir(parents=True)
    boot_jar.parent.mkdir()
    dex2oat.write_bytes(b"tool")
    boot_jar.write_bytes(b"dex")
    return argparse.Namespace(
        target_id="linux-x86_64-gnu",
        dex2oat=dex2oat,
        boot_jar=boot_jar,
        output_root=tmp_path / "runtime" / "boot-image",
        instruction_set="x86_64",
        parallel=32,
        library_dir=[dex2oat.parent],
        timeout=30,
    )


def test_boot_image_builder_is_shell_free_relocatable_and_atomic(
    tmp_path, monkeypatch
):
    args = _args(tmp_path)
    calls = []

    def run(command, **options):
        calls.append((command, options))
        image = Path(next(value.split("=", 1)[1] for value in command if value.startswith("--image=")))
        oat = Path(next(value.split("=", 1)[1] for value in command if value.startswith("--oat-file=")))
        image.write_bytes(b"ART-image")
        oat.write_bytes(b"ELF-oat")
        oat.with_suffix(".vdex").write_bytes(b"VDEX-data")
        return subprocess.CompletedProcess(command, 0, stdout="built\n", stderr="")

    monkeypatch.setattr(build_boot_image.subprocess, "run", run)
    output = build_boot_image.build_boot_image(args)

    command, options = calls[0]
    assert options["shell"] is False
    assert "--force-determinism" in command
    assert "--avoid-storing-invocation" in command
    assert "-Xmx512m" in command
    assert "-j32" in command
    assert options["env"]["LD_LIBRARY_PATH"] == str(args.dex2oat.parent)
    manifest_text = (output / "manifest.json").read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert manifest["target_id"] == "linux-x86_64-gnu"
    assert manifest["logical_boot_jar"] == "/system/framework/boot.jar"
    assert {entry["path"] for entry in manifest["artifacts"]} == {
        "x86_64/boot.art",
        "x86_64/boot.oat",
        "x86_64/boot.vdex",
    }
    assert str(tmp_path) not in manifest_text

    accepted = (output / "x86_64" / "boot.art").read_bytes()
    monkeypatch.setattr(
        build_boot_image.subprocess,
        "run",
        lambda command, **options: subprocess.CompletedProcess(
            command, 0, stdout="fatal but returned zero\n", stderr=""
        ),
    )
    with pytest.raises(build_boot_image.BootImageError, match="missing"):
        build_boot_image.build_boot_image(args)
    assert (output / "x86_64" / "boot.art").read_bytes() == accepted


def test_boot_image_builder_rejects_unbounded_parallelism(tmp_path):
    args = _args(tmp_path)
    args.parallel = 65
    with pytest.raises(build_boot_image.BootImageError, match="between 1 and 64"):
        build_boot_image.build_boot_image(args)
