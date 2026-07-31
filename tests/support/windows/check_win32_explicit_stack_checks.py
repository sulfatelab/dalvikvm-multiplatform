#!/usr/bin/env python3
"""Verify the unified Windows x64 explicit-stack-check source contract."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"FAIL {label}: missing {needle!r}")


def reject(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise SystemExit(f"FAIL {label}: found obsolete {needle!r}")


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise SystemExit(f"FAIL tool: not found: {name}")
    return path


def run(*args: str) -> str:
    result = subprocess.run(args, check=False, text=True, capture_output=True)
    if result.returncode != 0:
        raise SystemExit(
            f"FAIL command ({result.returncode}): {' '.join(args)}\n{result.stderr}"
        )
    return result.stdout


def find_one(root: Path, name: str) -> Path:
    matches = list(root.rglob(name))
    if len(matches) != 1:
        raise SystemExit(
            f"FAIL object: expected one {name!r} below {root}, found {len(matches)}"
        )
    return matches[0]


def read_define(header: str, name: str) -> int:
    match = re.search(rf"^#define {re.escape(name)} (\S+)$", header, re.MULTILINE)
    if match is None:
        raise SystemExit(f"FAIL asm defines: missing {name}")
    return int(match.group(1), 0)


def instruction_text(line: str) -> str | None:
    match = re.match(r"^\s*[0-9a-f]+:\s+(.*)$", line)
    return match.group(1).strip() if match is not None else None


def check_windows_x64_object(build: Path, objdump: str) -> None:
    object_root = build / "CMakeFiles/art.dir"
    nterp_obj = find_one(object_root, "mterp_x86_64.S.obj")
    defines_path = build / "gensrc/art/asm/include/asm_defines.h"
    if not defines_path.is_file():
        raise SystemExit(f"FAIL Windows x64 asm defines: missing {defines_path}")
    defines = defines_path.read_text(encoding="utf-8")
    stack_end = read_define(defines, "THREAD_STACK_END_OFFSET")
    throw_so = read_define(defines, "THREAD_THROW_STACK_OVERFLOW_ENTRYPOINT_OFFSET")

    disassembly = run(objdump, "-dr", "--no-show-raw-insn", str(nterp_obj))
    instructions = [
        text
        for line in disassembly.splitlines()
        if (text := instruction_text(line)) is not None
    ]
    compare = f"cmpq\t0x{stack_end:x}(%r15), %rsp"
    tail_jump = f"jmpq\t*0x{throw_so:x}(%r15)"
    compare_indices = [i for i, text in enumerate(instructions) if text == compare]
    if len(compare_indices) != 7:
        raise SystemExit(
            "FAIL Windows x64 nterp object: expected seven explicit stack compares "
            f"(entry plus six invokes), found {len(compare_indices)}"
        )
    for index in compare_indices:
        sequence = instructions[index : index + 3]
        if len(sequence) != 3 or not sequence[1].startswith("jae\t") or sequence[2] != tail_jump:
            raise SystemExit(
                "FAIL Windows x64 nterp object: malformed compare/branch/tail-jump sequence: "
                + " | ".join(sequence)
            )
    reject(disassembly, "-0x2000(%rsp)", "Windows x64 nterp implicit probe")


def check_linux_object(build: Path, objdump: str) -> None:
    object_root = build / "CMakeFiles/art.dir"
    nterp_obj = find_one(object_root, "mterp_x86_64.S.o")
    disassembly = run(objdump, "-dr", "--no-show-raw-insn", str(nterp_obj))
    probe = "testq\t%rax, -0x2000(%rsp)"
    count = sum(
        instruction_text(line) == probe
        for line in disassembly.splitlines()
    )
    if count != 7:
        raise SystemExit(
            "FAIL Linux nterp object: expected seven existing implicit probes "
            f"(entry plus six invokes), found {count}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[3],
    )
    parser.add_argument(
        "--win-build",
        type=Path,
        default=None,
        help="configured Windows x64 build directory; enables object verification",
    )
    parser.add_argument(
        "--linux-build",
        type=Path,
        default=None,
        help="configured Linux build directory; enables object verification",
    )
    args = parser.parse_args()
    repo = args.repo.resolve()
    art = repo / "vendor/art"

    runtime = (art / "runtime/runtime.cc").read_text(encoding="utf-8")
    thread = (art / "runtime/thread.cc").read_text(encoding="utf-8")
    stack = (
        art / "runtime/multiplatform/windows/stack_windows.cc"
    ).read_text(encoding="utf-8")
    codegen = (
        art / "compiler/optimizing/code_generator_x86_64.cc"
    ).read_text(encoding="utf-8")
    nterp = (
        art / "runtime/interpreter/mterp/x86_64ng/main.S"
    ).read_text(encoding="utf-8")
    definitions = (
        art / "tools/cpp-define-generator/thread.def"
    ).read_text(encoding="utf-8")

    require(runtime, "implicit_so_checks_ = false;", "runtime flag")
    require(thread, "InspectWin32StackLayout(read_stack_base,", "stack accounting")
    reject(thread, "InstallWin32StackProtection(read_stack_base,", "stack accounting")
    require(stack, "bool InspectWin32StackLayout(", "layout inspector")
    require(stack, "minimum_usable_size - system_page_size", "layout minimum")

    require(codegen, "Thread::StackEndOffset<kX86_64PointerSize>()", "optimizing compare")
    require(codegen, "__ j(kAboveEqual, &stack_ok);", "optimizing boundary")
    require(codegen, "kQuickThrowStackOverflow", "optimizing tail throw")
    require(
        codegen,
        "__ testq(CpuRegister(RAX), Address(CpuRegister(RSP),",
        "Linux optimizing probe",
    )

    require(nterp, "cmpq THREAD_STACK_END_OFFSET(rSELF), %rsp", "nterp compare")
    require(nterp, "jmpq *THREAD_THROW_STACK_OVERFLOW_ENTRYPOINT_OFFSET(rSELF)", "nterp tail throw")
    require(nterp, "testq %rax, -STACK_OVERFLOW_RESERVED_BYTES(%rsp)", "Linux nterp probe")
    if nterp.count("CHECK_STACK_OVERFLOW") != 3:
        raise SystemExit("FAIL nterp checks: expected one macro and two uses")

    require(definitions, "ASM_DEFINE(THREAD_STACK_END_OFFSET,", "stack-end definition")
    require(
        definitions,
        "ASM_DEFINE(THREAD_THROW_STACK_OVERFLOW_ENTRYPOINT_OFFSET,",
        "throw-entrypoint definition",
    )

    objdump = require_tool(os.environ.get("LLVM_OBJDUMP", "llvm-objdump"))
    if args.win_build is not None:
        check_windows_x64_object(args.win_build.resolve(), objdump)
    if args.linux_build is not None:
        check_linux_object(args.linux_build.resolve(), objdump)

    checked = []
    if args.win_build is not None:
        checked.append("Windows x64 object")
    if args.linux_build is not None:
        checked.append("Linux object")
    suffix = f" ({', '.join(checked)})" if checked else ""
    print(f"Windows x64 explicit stack-check contract: PASS{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
