#!/usr/bin/env python3
"""Verify the Windows x64 W-002 rSELF and OSR managed-entry contracts."""

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
        "Windows x64 quick OSR source",
        [
            "#if defined(_WIN32)",
            "movq 0x28(%rsp), %r10",
            "movq 0x30(%rsp), %r11",
            "PUSH rbp",
            "PUSH rdi",
            "PUSH rsi",
            "movq %rcx, %rdi",
            "movq %rdx, %rsi",
            "movq %r8, %rdx",
            "movq %r9, %rcx",
            "movq %r10, %r8",
            "movq %r11, %r9",
            "subq LITERAL(160), %rsp",
            "movdqu %xmm6, 0(%rsp)",
            ".seh_savexmm %xmm6, 64",
            "movdqu %xmm11, 80(%rsp)",
            ".seh_savexmm %xmm11, 144",
            "movdqu %xmm15, 144(%rsp)",
            ".seh_savexmm %xmm15, 208",
            "PUSH r15",
            "movq %r9, %r15",
            "movq %rsp, %r12",
            ".seh_setframe %r12, 0",
            "jmp .Losr_call",
            ".Losr_entry:",
            "CFI_RESTORE_STATE_AND_DEF_CFA rsp, 256",
            "CFI_DEF_CFA_REGISTER(r12)",
            "movq %rsp, %rbp",
            "jmp *%rdx",
            ".Losr_call:",
            "call .Losr_entry",
            ".seh_endproc",
        ],
    )
    quick_osr_return = source_function(
        quick,
        ".Losr_return:",
        ".seh_endproc",
    )
    require_ordered(
        quick_osr_return,
        "Windows x64 quick OSR return source",
        [
            ".Losr_return:",
            ".seh_stackalloc 248",
            ".seh_savexmm %xmm15, 208",
            ".seh_savereg %rbp, 240",
            "movq 8(%rsp), %r15",
            "movdqu 64(%rsp), %xmm6",
            "movdqu 144(%rsp), %xmm11",
            "movdqu 208(%rsp), %xmm15",
            "movq 240(%rsp), %rbp",
            "addq LITERAL(248), %rsp",
            "ret",
        ],
    )
    if "CFI_RESTORE_STATE_AND_DEF_CFA rsp, 256" not in quick_osr:
        fail("Windows x64 quick OSR CFA does not include the RDI/RSI and XMM saves")
    if "CFI_RESTORE_STATE_AND_DEF_CFA rsp, 80" not in quick_osr:
        fail("the Linux quick OSR CFA path changed")
    if re.search(
        r"\.Losr_entry:\s*\n"
        r"\s*CFI_RESTORE_STATE_AND_DEF_CFA rsp, 256\s*\n"
        r"#if defined\(_WIN32\)\s*\n"
        r"\s*CFI_DEF_CFA_REGISTER\(r12\)\s*\n"
        r"#else\s*\n"
        r"\s*CFI_DEF_CFA_REGISTER\(rbp\)\s*\n"
        r"#endif",
        quick_osr,
    ) is None:
        fail("quick OSR CFA register must remain R12 on Windows x64 and RBP on Linux")

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
        "Windows x64 nterp OSR source",
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
        fail("Windows x64 ThreadOffsetAddr no longer uses R15")

    codegen = (
        art / "compiler/optimizing/code_generator_x86_64.cc"
    ).read_text(encoding="utf-8")
    blocked = source_function(
        codegen,
        "inline RegisterSet CodeGeneratorX86_64::ComputeBlockedRegisters() const {",
        "return blocked_registers;\n}",
    )
    require_ordered(
        blocked,
        "Windows x64 optimizing blocked-register source",
        [
            "#if defined(_WIN32) || defined(ART_TARGET_WINDOWS)",
            "core_registers |= (1u << R15);",
            "if (GetCompilerOptions().IsJitCompiler()) {",
            "core_registers |= (1u << RBP);",
            "#endif",
        ],
    )
    if blocked.count("core_registers |= (1u << R15);") != 1:
        fail("Windows x64 optimizing compiler no longer blocks R15")
    if blocked.count("core_registers |= (1u << RBP);") != 1:
        fail("Windows x64 JIT optimizing compiler no longer blocks its RBP frame anchor")
    if "{ RBX, RBP, R12, R13, R14 };" not in codegen:
        fail("Windows x64 compiled callee-save set unexpectedly includes R15")


def check_objects(repo: Path, build: Path, objdump: str, readobj: str) -> None:
    object_root = build / "CMakeFiles/art.dir"
    quick_obj = find_one(object_root, "quick_entrypoints_x86_64.S.obj")
    nterp_obj = find_one(object_root, "mterp_x86_64.S.obj")
    jit_obj = find_one(object_root, "jit.cc.obj")

    quick_dis = run(objdump, "-dr", "--no-show-raw-insn", str(quick_obj))
    quick_osr = object_function(quick_dis, "art_quick_osr_stub")
    require_ordered(
        quick_osr,
        "Windows x64 quick OSR object",
        [
            "movq\t0x28(%rsp), %r10",
            "movq\t0x30(%rsp), %r11",
            "pushq\t%rbp",
            "pushq\t%rdi",
            "pushq\t%rsi",
            "movq\t%rcx, %rdi",
            "movq\t%rdx, %rsi",
            "movq\t%r8, %rdx",
            "movq\t%r9, %rcx",
            "subq\t$0xa0, %rsp",
            "movdqu\t%xmm6, (%rsp)",
            "movdqu\t%xmm11, 0x50(%rsp)",
            "movdqu\t%xmm15, 0x90(%rsp)",
            "pushq\t%r15",
            "movq\t%r9, %r15",
            "movq\t%rsp, %r12",
            "jmp\t",
            "subq\t%rcx, %rsp",
            "movq\t%rsp, %rbp",
            "jmpq\t*%rdx",
            "callq\t",
            "movq\t0x8(%rsp), %r15",
            "movdqu\t0x40(%rsp), %xmm6",
            "movdqu\t0x90(%rsp), %xmm11",
            "movdqu\t0xd0(%rsp), %xmm15",
            "movq\t0xe0(%rsp), %rsi",
            "movq\t0xe8(%rsp), %rdi",
            "movq\t0xf0(%rsp), %rbp",
            "addq\t$0xf8, %rsp",
        ],
    )

    nterp_dis = run(objdump, "-dr", "--no-show-raw-insn", str(nterp_obj))
    nterp_hotness = object_function(nterp_dis, "NterpHotnessCheck")
    require_ordered(
        nterp_hotness,
        "Windows x64 nterp OSR object",
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
        fail("Windows x64 nterp object must contain exactly one NterpFree relocation")
    if re.search(r"\bfree\b", nterp_relocations):
        fail("Windows x64 nterp object still directly relocates UCRT free")

    jit_relocations = run(readobj, "--relocations", str(jit_obj))
    if jit_relocations.count("art_quick_osr_stub") != 1:
        fail("jit.cc object must call art_quick_osr_stub exactly once")


def main() -> int:
    repo = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build",
        type=Path,
        default=repo / "out/windows-x86_64-msvc/RelWithDebInfo",
        help="configured Windows x64 build directory",
    )
    args = parser.parse_args()
    build = args.build.resolve()
    if not (build / "art.dll").is_file():
        fail(f"required Windows x64 artifact is missing: {build / 'art.dll'}")

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
