#!/usr/bin/env python3
"""Verify the Win64 W-002 rSELF and OSR managed-entry contracts."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys


def fail(message: str) -> None:
    raise RuntimeError(message)


def run(tool: str, *args: str) -> str:
    result = subprocess.run([tool, *args], text=True, capture_output=True)
    if result.returncode != 0:
        fail(
            f"command failed ({result.returncode}): {tool} {' '.join(args)}\n"
            f"{result.stdout}{result.stderr}"
        )
    return result.stdout


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        fail(f"required tool is missing: {name}")
    return path


def find_one(root: Path, name: str) -> Path:
    matches = sorted(root.rglob(name))
    if len(matches) != 1:
        fail(f"expected one {name} below {root}, found {len(matches)}")
    return matches[0]


def require_ordered(text: str, label: str, tokens: list[str]) -> None:
    offset = 0
    for token in tokens:
        found = text.find(token, offset)
        if found < 0:
            fail(f"{label} is missing ordered token: {token}")
        offset = found + len(token)


def source_function(text: str, start: str, end: str) -> str:
    begin = text.find(start)
    if begin < 0:
        fail(f"source function start not found: {start}")
    finish = text.find(end, begin)
    if finish < 0:
        fail(f"source function end not found: {end}")
    return text[begin : finish + len(end)]


def object_function(disassembly: str, symbol: str) -> str:
    match = re.search(
        rf"^[0-9a-f]+ <{re.escape(symbol)}>:\n(?P<body>.*?)(?=\n[0-9a-f]+ <|\Z)",
        disassembly,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        fail(f"object function not found: {symbol}")
    return match.group("body")


def check_source(repo: Path) -> None:
    art = repo / "vendor/art"
    jit = (art / "runtime/jit/jit.cc").read_text(encoding="utf-8")
    declaration = source_function(
        jit,
        'extern "C" void art_quick_osr_stub(',
        "Thread* self);",
    )
    if "ART_QUICK_ENTRYPOINT_ABI" in declaration:
        fail("art_quick_osr_stub must retain the normal platform C++ ABI")

    quick = (
        art / "runtime/arch/x86_64/quick_entrypoints_x86_64.S"
    ).read_text(encoding="utf-8")
    quick_osr = source_function(
        quick,
        "DEFINE_FUNCTION art_quick_osr_stub",
        "END_FUNCTION art_quick_osr_stub",
    )
    require_ordered(
        quick_osr,
        "Win64 quick OSR source",
        [
            "#if defined(_WIN32)",
            "PUSH rdi",
            "PUSH rsi",
            "movq 0x38(%rsp), %r10",
            "movq 0x40(%rsp), %r11",
            "movq %rcx, %rdi",
            "movq %rdx, %rsi",
            "movq %r8, %rdx",
            "movq %r9, %rcx",
            "movq %r10, %r8",
            "movq %r11, %r9",
            "PUSH r15",
            "movq %r9, %r15",
            "POP r15",
            "POP rsi",
            "POP rdi",
            "jmp *%rdx",
        ],
    )
    if "CFI_RESTORE_STATE_AND_DEF_CFA rsp, 96" not in quick_osr:
        fail("Win64 quick OSR CFA does not include the RDI/RSI saves")
    if "CFI_RESTORE_STATE_AND_DEF_CFA rsp, 80" not in quick_osr:
        fail("the Linux quick OSR CFA path changed")

    nterp = (
        art / "runtime/interpreter/mterp/x86_64ng/main.S"
    ).read_text(encoding="utf-8")
    hotness = source_function(
        nterp,
        "NterpHotnessCheck:",
        "NterpHandleInvokeInterfaceOnObjectMethodRange:",
    )
    require_ordered(
        hotness,
        "Win64 nterp OSR source",
        [
            "#if defined(_WIN32)",
            "movq -8(rREFS), %rsp",
            "movq %rsp, %r14",
            "movq OSR_DATA_NATIVE_PC(%rax), %rbx",
            "pushq LITERAL(0)",
            "call .Lnterp_osr_entry_win",
            "RESTORE_ALL_CALLEE_SAVES",
            "ret",
            ".Lnterp_osr_entry_win:",
            "movq OSR_DATA_FRAME_SIZE(%rax), %rcx",
            "subq $$8, %rcx",
            "call SYMBOL(NterpFree)",
            "jmp *%rbx",
            "#else",
            "subq $$CALLEE_SAVES_SIZE, %rcx",
            "call free",
            "#endif",
        ],
    )

    nterp_cc = (
        art / "runtime/interpreter/mterp/nterp.cc"
    ).read_text(encoding="utf-8")
    if 'extern "C" NTERP_C_ABI void NterpFree(void* val)' not in nterp_cc:
        fail("NterpFree is not exposed with the assembly-facing ABI")

    assembler = (
        art / "compiler/utils/x86_64/assembler_x86_64.h"
    ).read_text(encoding="utf-8")
    if "return Address(CpuRegister(R15), offset);" not in assembler:
        fail("Win64 ThreadOffsetAddr no longer uses R15")

    codegen = (
        art / "compiler/optimizing/code_generator_x86_64.cc"
    ).read_text(encoding="utf-8")
    if "| (1u << R15)" not in codegen:
        fail("Win64 optimizing compiler no longer blocks R15")
    if "{ RBX, RBP, R12, R13, R14 };" not in codegen:
        fail("Win64 compiled callee-save set unexpectedly includes R15")


def check_objects(repo: Path, build: Path, objdump: str, readobj: str) -> None:
    object_root = build / "CMakeFiles/art.dir"
    quick_obj = find_one(object_root, "quick_entrypoints_x86_64.S.obj")
    nterp_obj = find_one(object_root, "mterp_x86_64.S.obj")
    jit_obj = find_one(object_root, "jit.cc.obj")

    quick_dis = run(objdump, "-dr", "--no-show-raw-insn", str(quick_obj))
    quick_osr = object_function(quick_dis, "art_quick_osr_stub")
    require_ordered(
        quick_osr,
        "Win64 quick OSR object",
        [
            "pushq\t%rdi",
            "pushq\t%rsi",
            "movq\t0x38(%rsp), %r10",
            "movq\t0x40(%rsp), %r11",
            "movq\t%rcx, %rdi",
            "movq\t%rdx, %rsi",
            "movq\t%r8, %rdx",
            "movq\t%r9, %rcx",
            "pushq\t%r15",
            "movq\t%r9, %r15",
            "popq\t%r15",
            "popq\t%rsi",
            "popq\t%rdi",
            "jmpq\t*%rdx",
        ],
    )

    nterp_dis = run(objdump, "-dr", "--no-show-raw-insn", str(nterp_obj))
    nterp_hotness = object_function(nterp_dis, "NterpHotnessCheck")
    require_ordered(
        nterp_hotness,
        "Win64 nterp OSR object",
        [
            "movq\t-0x8(%rbp), %rsp",
            "movq\t%rsp, %r14",
            "pushq\t$0x0",
            "callq",
            "addq\t$0x8, %rsp",
            "popq\t%rbp",
            "popq\t%r15",
            "retq",
            "subq\t$0x8, %rcx",
            "IMAGE_REL_AMD64_REL32\tNterpFree",
            "jmpq\t*%rbx",
        ],
    )
    nterp_relocations = run(readobj, "--relocations", str(nterp_obj))
    if nterp_relocations.count("NterpFree") != 1:
        fail("Win64 nterp object must contain exactly one NterpFree relocation")
    if re.search(r"\bfree\b", nterp_relocations):
        fail("Win64 nterp object still directly relocates UCRT free")

    jit_relocations = run(readobj, "--relocations", str(jit_obj))
    if jit_relocations.count("art_quick_osr_stub") != 1:
        fail("jit.cc object must call art_quick_osr_stub exactly once")


def main() -> int:
    repo = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build",
        type=Path,
        default=repo / "build/win64_phase1",
        help="configured Win64 build directory",
    )
    args = parser.parse_args()
    build = args.build.resolve()
    if not (build / "art.dll").is_file():
        fail(f"required Win64 artifact is missing: {build / 'art.dll'}")

    objdump = require_tool("llvm-objdump")
    readobj = require_tool("llvm-readobj")
    check_source(repo)
    check_objects(repo, build, objdump, readobj)
    print("W-002 managed-entry structural check: PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        print(f"W-002 managed-entry structural check: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
