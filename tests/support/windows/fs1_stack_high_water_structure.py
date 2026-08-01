#!/usr/bin/env python3
"""Verify FS-1 is probe-only and samples the generated/assembly failure paths."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import subprocess


def fail(message: str) -> None:
    raise SystemExit(f"FS-1 structural check FAIL: {message}")


def run(*args: str) -> str:
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        fail(f"command exited {result.returncode}: {' '.join(args)}\n{result.stderr}")
    return result.stdout


def require_tool(name: str, explicit: Path | None = None) -> str:
    if explicit is not None:
        tool = str(explicit.resolve())
        if not explicit.is_file():
            fail(f"configured tool does not exist: {explicit}")
        return tool
    tool = shutil.which(name)
    if tool is None:
        fail(f"missing tool {name}")
    return tool


def find_one(root: Path, name: str) -> Path:
    matches = list(root.rglob(name))
    if len(matches) != 1:
        fail(f"expected one {name} below {root}, found {len(matches)}")
    return matches[0]


def read_define(text: str, name: str) -> int:
    match = re.search(rf"^#define {re.escape(name)} (\S+)$", text, re.MULTILINE)
    if match is None:
        fail(f"instrumented asm definitions omit {name}")
    return int(match.group(1), 0)


def instruction_text(line: str) -> str | None:
    match = re.match(r"^\s*[0-9a-f]+:\s+(.*)$", line)
    return match.group(1).strip() if match is not None else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--product-build", type=Path)
    parser.add_argument("--probe-build", type=Path, required=True)
    parser.add_argument("--llvm-readobj", type=Path)
    parser.add_argument("--llvm-objdump", type=Path)
    args = parser.parse_args()

    repo = args.repo.resolve()
    product = args.product_build.resolve() if args.product_build else None
    probe = args.probe_build.resolve()
    readobj = require_tool("llvm-readobj", args.llvm_readobj)
    objdump = require_tool("llvm-objdump", args.llvm_objdump)

    symbol = "artWin32DumpStackOverflowHighWater"
    probe_exports = run(readobj, "--coff-exports", str(probe / "art.dll"))
    if product is not None:
        product_exports = run(readobj, "--coff-exports", str(product / "art.dll"))
        if f"Name: {symbol}" in product_exports:
            fail(f"product art.dll unexpectedly exports {symbol}")
    if f"Name: {symbol}" not in probe_exports:
        fail(f"instrumented art.dll does not export {symbol}")

    probe_defines_path = probe / "gensrc/art/asm/include/asm_defines.h"
    defines = probe_defines_path.read_text(encoding="utf-8")
    if product is not None:
        product_defines_path = product / "gensrc/art/asm/include/asm_defines.h"
        product_defines = product_defines_path.read_text(encoding="utf-8")
        if "THREAD_WIN32_STACK_HIGH_WATER_" in product_defines:
            fail("product asm definitions contain FS-1 offsets")

    stack_end = read_define(defines, "THREAD_STACK_END_OFFSET")
    throw_entry = read_define(defines, "THREAD_THROW_STACK_OVERFLOW_ENTRYPOINT_OFFSET")
    explicit = read_define(defines, "THREAD_WIN32_STACK_HIGH_WATER_EXPLICIT_CHECK_OFFSET")
    sequence = read_define(defines, "THREAD_WIN32_STACK_HIGH_WATER_SEQUENCE_OFFSET")
    active = read_define(defines, "THREAD_WIN32_STACK_HIGH_WATER_ACTIVE_OFFSET")
    quick_entry = read_define(defines, "THREAD_WIN32_STACK_HIGH_WATER_QUICK_ENTRYPOINT_OFFSET")
    quick_frame = read_define(defines, "THREAD_WIN32_STACK_HIGH_WATER_QUICK_FRAME_OFFSET")
    long_jump = read_define(defines, "THREAD_WIN32_STACK_HIGH_WATER_LONG_JUMP_OFFSET")

    nterp_obj = find_one(probe / "CMakeFiles/art.dir", "mterp_x86_64.S.obj")
    nterp_disassembly = run(objdump, "-dr", "--no-show-raw-insn", str(nterp_obj))
    instructions = [
        instruction
        for line in nterp_disassembly.splitlines()
        if (instruction := instruction_text(line)) is not None
    ]
    compare = f"cmpq\t0x{stack_end:x}(%r15), %rsp"
    store = f"movq\t%rsp, 0x{explicit:x}(%r15)"
    jump = f"jmpq\t*0x{throw_entry:x}(%r15)"
    compare_indices = [index for index, instruction in enumerate(instructions) if instruction == compare]
    if len(compare_indices) != 7:
        fail(f"instrumented nterp has {len(compare_indices)} checks, expected seven")
    for index in compare_indices:
        path = instructions[index : index + 4]
        if len(path) != 4 or not path[1].startswith("jae\t") or path[2:] != [store, jump]:
            fail("nterp failure path is not compare/branch/direct-RSP-store/tail-jump: " + " | ".join(path))

    quick_obj = find_one(probe / "CMakeFiles/art.dir", "quick_entrypoints_x86_64.S.obj")
    quick_disassembly = run(objdump, "-dr", "--no-show-raw-insn", str(quick_obj))
    required_quick_instructions = (
        f"incq\t0x{sequence:x}(%r15)",
        f"movq\t$0x1, 0x{active:x}(%r15)",
        f"movq\t%rsp, 0x{quick_entry:x}(%r15)",
        f"movq\t%rsp, 0x{quick_frame:x}(%r15)",
        f"movq\t%rsp, 0x{long_jump:x}(%r15)",
    )
    for instruction in required_quick_instructions:
        if instruction not in quick_disassembly:
            fail(f"quick object omits direct sample {instruction!r}")

    codegen = (repo / "vendor/art/compiler/optimizing/code_generator_x86_64.cc").read_text(
        encoding="utf-8"
    )
    match = re.search(
        r"__ j\(kAboveEqual, &stack_ok\);(?P<failure>.*?)"
        r"__ gs\(\)->jmp\(Address::ThreadOffsetAddr\(",
        codegen,
        re.DOTALL,
    )
    if match is None or "kExplicitCheck" not in match.group("failure") or "CpuRegister(RSP)" not in match.group("failure"):
        fail("optimizing failing branch does not directly store RSP before the tail throw")

    thread = (repo / "vendor/art/runtime/thread.h").read_text(encoding="utf-8")
    common = (repo / "vendor/art/runtime/common_throws.cc").read_text(encoding="utf-8")
    if "Probe-only, thread-owned storage" not in thread:
        fail("thread-owned fixed probe record is missing")
    if "std::string" in re.search(
        r"struct Win32StackOverflowHighWater \{.*?\n\};", thread, re.DOTALL
    ).group(0):
        fail("critical-path probe record contains allocating string state")
    for phase in (
        "kThrowEntrypoint",
        "kExpandedStackEnd",
        "kExceptionConstruction",
        "kExceptionConstructed",
        "kDefaultStackEndRestored",
    ):
        if phase not in common:
            fail(f"common throw path omits {phase}")

    print(
        "FS-1 stack high-water structural check: PASS "
        "(product-isolated, optimizing direct store, nterp=7, quick/long-jump direct stores)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
