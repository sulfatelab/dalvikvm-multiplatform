import argparse
from pathlib import Path
import subprocess

import pytest

from tests.support import generate_conscrypt_constants


def _arguments(tmp_path: Path) -> argparse.Namespace:
    compiler = tmp_path / "toolchain" / "bin" / "clang++"
    compiler.parent.mkdir(parents=True)
    compiler.write_bytes(b"plain clang driver")
    source = tmp_path / "source" / "GenerateConstants.cpp"
    source.parent.mkdir()
    source.write_text("int main() { return 0; }\n", encoding="utf-8")
    include_dir = tmp_path / "include"
    include_dir.mkdir()
    return argparse.Namespace(
        compiler=compiler,
        source=source,
        include_dir=include_dir,
        work_root=tmp_path / "out" / "work",
        output=tmp_path / "out" / "generated" / "NativeConstants.java",
        package="com.android.org.conscrypt",
        compile_option=["--target=x86_64-pc-windows-msvc", "-nostdinc++"],
        link_option=["-fuse-ld=lld", "ucrt.lib"],
    )


def test_generation_uses_plain_clang_without_shell_and_normalizes_output(
    tmp_path, monkeypatch
):
    args = _arguments(tmp_path)
    commands = []

    def run(command, **kwargs):
        commands.append((command, kwargs))
        if command[0] == str(args.compiler):
            executable = Path(command[command.index("-o") + 1])
            executable.write_bytes(b"host generator")
            return subprocess.CompletedProcess(command, 0, "compile output\n", "")
        return subprocess.CompletedProcess(
            command,
            0,
            "package com.android.org.conscrypt;\r\nfinal class NativeConstants {}\r\n",
            "generator diagnostic\n",
        )

    monkeypatch.setattr(generate_conscrypt_constants.subprocess, "run", run)

    generate_conscrypt_constants.generate(args)
    first = args.output.read_bytes()
    generate_conscrypt_constants.generate(args)

    assert args.output.read_bytes() == first
    assert first == (
        b"package com.android.org.conscrypt;\nfinal class NativeConstants {}\n"
    )
    assert commands[0][0][0] == str(args.compiler)
    assert commands[0][0][1:3] == ["-std=c++17", "-O0"]
    assert commands[0][0][3:5] == args.compile_option
    assert commands[0][0][-2:] == args.link_option
    assert commands[1][0][1] == args.package
    assert all(options["shell"] is False for _, options in commands)
    assert (args.work_root / "compile.stdout.txt").read_text(encoding="utf-8") == (
        "compile output\n"
    )
    assert (args.work_root / "generator.stderr.txt").read_text(
        encoding="utf-8"
    ) == "generator diagnostic\n"


def test_generation_rejects_non_plain_clang_driver(tmp_path):
    args = _arguments(tmp_path)
    args.compiler = args.compiler.with_name("clang-cl.exe")
    args.compiler.write_bytes(b"clang-cl driver")

    with pytest.raises(
        generate_conscrypt_constants.GenerationError,
        match=r"plain Clang\+\+ driver required",
    ):
        generate_conscrypt_constants.generate(args)


def test_generation_rejects_multiline_driver_option(tmp_path):
    args = _arguments(tmp_path)
    args.link_option = ["kernel32.lib\nforbidden"]

    with pytest.raises(
        generate_conscrypt_constants.GenerationError,
        match="invalid host link option",
    ):
        generate_conscrypt_constants.generate(args)
