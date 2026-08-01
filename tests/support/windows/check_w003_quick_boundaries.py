#!/usr/bin/env python3
"""Verify W-003 quick-frame traps and Microsoft XMM boundary preservation."""

from __future__ import annotations

import argparse
from collections import Counter
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


BOUNDARY_SYMBOLS = (
    "art_quick_invoke_stub",
    "art_quick_invoke_static_stub",
    "art_quick_osr_stub",
)


def fail(message: str) -> None:
    raise RuntimeError(message)


def run(tool: Path, *args: str) -> str:
    result = subprocess.run([str(tool), *args], text=True, capture_output=True)
    if result.returncode != 0:
        fail(
            f"command failed ({result.returncode}): {tool} {' '.join(args)}\n"
            f"{result.stdout}{result.stderr}"
        )
    return result.stdout


def require_tool(path: Path) -> Path:
    path = path.absolute()
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = os.lstat(current)
        except OSError as exc:
            fail(f"cannot inspect configured LLVM tool path {current}: {exc}")
        attributes = getattr(info, "st_file_attributes", 0)
        if stat.S_ISLNK(info.st_mode) or (
            attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        ):
            fail(f"configured LLVM tool path contains a link/reparse point: {current}")
    if not path.is_file():
        fail(f"configured LLVM tool is not a regular file: {path}")
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


def source_region(text: str, start: str, end: str) -> str:
    begin = text.find(start)
    if begin < 0:
        fail(f"source region start not found: {start}")
    finish = text.find(end, begin)
    if finish < 0:
        fail(f"source region end not found after {start}: {end}")
    return text[begin : finish + len(end)]


def source_function(text: str, symbol: str) -> str:
    return source_region(
        text,
        f"DEFINE_FUNCTION {symbol}",
        f"END_FUNCTION {symbol}",
    )


def object_function(disassembly: str, symbol: str) -> str:
    match = re.search(
        rf"^[0-9a-f]+ <{re.escape(symbol)}>:\n(?P<body>.*?)(?=\n[0-9a-f]+ <|\Z)",
        disassembly,
        re.MULTILINE | re.DOTALL,
    )
    if match is None:
        fail(f"object function not found: {symbol}")
    return match.group("body")


def trap_distribution(disassembly: str) -> Counter[str]:
    distribution: Counter[str] = Counter()
    current: str | None = None
    for line in disassembly.splitlines():
        match = re.match(r"^[0-9a-f]+ <([^>]+)>:$", line)
        if match is not None:
            current = match.group(1)
        elif re.search(r"\bint3\b", line):
            if current is None:
                fail("int3 instruction found outside an object function")
            distribution[current] += 1
    return distribution


def check_setup_source(quick: str, support: str) -> None:
    frame_macros = {
        "SETUP_SAVE_REFS_ONLY_FRAME": source_region(
            support, "MACRO0(SETUP_SAVE_REFS_ONLY_FRAME)", "END_MACRO"
        ),
        "SETUP_SAVE_REFS_AND_ARGS_FRAME": source_region(
            quick, "MACRO0(SETUP_SAVE_REFS_AND_ARGS_FRAME)", "END_MACRO"
        ),
        "SETUP_SAVE_ALL_CALLEE_SAVES_FRAME": source_region(
            support, "MACRO0(SETUP_SAVE_ALL_CALLEE_SAVES_FRAME)", "END_MACRO"
        ),
        "SETUP_SAVE_EVERYTHING_FRAME_R14_R15_SAVED": source_region(
            quick,
            "MACRO1(SETUP_SAVE_EVERYTHING_FRAME_R14_R15_SAVED",
            "END_MACRO",
        ),
    }
    for name, body in frame_macros.items():
        if "#if defined(_WIN32)" in body or "#if !defined(_WIN32)" in body:
            fail(f"{name} has regained a Windows-specific body")
        if "int3" in body and "#if defined(__APPLE__)" not in body:
            fail(f"{name} contains a non-Apple trap")
        if "THREAD_STORE_Q rsp, THREAD_TOP_QUICK_FRAME_OFFSET" not in body:
            fail(f"{name} does not publish the canonical top quick frame")


def check_boundary_source(quick: str) -> None:
    save = source_region(quick, "MACRO0(SAVE_WINDOWS_X64_NATIVE_XMMS)", "END_MACRO")
    restore = source_region(
        quick, "MACRO0(RESTORE_WINDOWS_X64_NATIVE_XMMS)", "END_MACRO"
    )
    require_ordered(
        save,
        "Windows x64 XMM save macro",
        [
            "#if defined(_WIN32)",
            "subq LITERAL(160), %rsp",
            "movdqu %xmm6, 0(%rsp)",
            "movdqu %xmm7, 16(%rsp)",
            "movdqu %xmm8, 32(%rsp)",
            "movdqu %xmm9, 48(%rsp)",
            "movdqu %xmm10, 64(%rsp)",
            "movdqu %xmm11, 80(%rsp)",
            "movdqu %xmm12, 96(%rsp)",
            "movdqu %xmm13, 112(%rsp)",
            "movdqu %xmm14, 128(%rsp)",
            "movdqu %xmm15, 144(%rsp)",
            "#endif",
        ],
    )
    require_ordered(
        restore,
        "Windows x64 XMM restore macro",
        [
            "#if defined(_WIN32)",
            "movdqu 0(%rsp), %xmm6",
            "movdqu 16(%rsp), %xmm7",
            "movdqu 32(%rsp), %xmm8",
            "movdqu 48(%rsp), %xmm9",
            "movdqu 64(%rsp), %xmm10",
            "movdqu 80(%rsp), %xmm11",
            "movdqu 96(%rsp), %xmm12",
            "movdqu 112(%rsp), %xmm13",
            "movdqu 128(%rsp), %xmm14",
            "movdqu 144(%rsp), %xmm15",
            "addq LITERAL(160), %rsp",
            "#endif",
        ],
    )
    # All three Windows x64 boundary stubs carry inline saves so their PE unwind
    # directives describe every XMM store. The one textual shared save/restore
    # site is the Linux side of the OSR preprocessor branch.
    if quick.count("    SAVE_WINDOWS_X64_NATIVE_XMMS\n") != 1:
        fail("expected exactly one shared Windows x64 native XMM save site for OSR")
    if quick.count("    RESTORE_WINDOWS_X64_NATIVE_XMMS\n") != 3:
        fail("expected exactly three Windows x64 native XMM restore sites")

    for symbol, xmm_label, gpr_label in (
        ("art_quick_invoke_stub", ".Lxmm_setup_finished", ".Lgpr_setup_finished"),
        (
            "art_quick_invoke_static_stub",
            ".Lxmm_setup_finished2",
            ".Lgpr_setup_finished2",
        ),
    ):
        body = source_function(quick, symbol)
        require_ordered(
            body,
            f"{symbol} source",
            [
                "pushq %rdi",
                "pushq %rsi",
                "movq 0x38(%rsp), %r10",
                "movq 0x40(%rsp), %r11",
                "subq LITERAL(160), %rsp",
                "movdqu %xmm6, 0(%rsp)",
                ".seh_savexmm %xmm6, 64",
                "movdqu %xmm11, 80(%rsp)",
                ".seh_savexmm %xmm11, 144",
                "movdqu %xmm15, 144(%rsp)",
                ".seh_savexmm %xmm15, 208",
                f"LOOP_OVER_SHORTY_LOADING_XMMS xmm6, {xmm_label}",
                f"{gpr_label}:",
                "call *ART_METHOD_QUICK_CODE_OFFSET_64(%rdi)",
                "POP rbp",
                "RESTORE_WINDOWS_X64_NATIVE_XMMS",
                "popq %rsi",
                "popq %rdi",
            ],
        )

    osr = source_function(quick, "art_quick_osr_stub")
    require_ordered(
        osr,
        "art_quick_osr_stub source",
        [
            "movq 0x28(%rsp), %r10",
            "movq 0x30(%rsp), %r11",
            "PUSH rbp",
            "PUSH rdi",
            "PUSH rsi",
            "subq LITERAL(160), %rsp",
            "movdqu %xmm6, 0(%rsp)",
            ".seh_savexmm %xmm6, 64",
            "movdqu %xmm11, 80(%rsp)",
            ".seh_savexmm %xmm11, 144",
            "movdqu %xmm15, 144(%rsp)",
            ".seh_savexmm %xmm15, 208",
            "PUSH r15",
            ".seh_pushreg %r15",
            "pushq LITERAL(0)",
            ".seh_stackalloc 8",
            "movq %rsp, %r12",
            ".seh_setframe %r12, 0",
            ".seh_endprologue",
            "jmp .Losr_call",
            ".Losr_entry:",
            "CFI_RESTORE_STATE_AND_DEF_CFA rsp, 256",
            "CFI_DEF_CFA_REGISTER(r12)",
            "movq %rsp, %rbp",
            "jmp *%rdx",
            ".Losr_call:",
            "call .Losr_entry",
            ".seh_endproc",
            "#else",
            "POP r15",
            "POP rbp",
            "RESTORE_WINDOWS_X64_NATIVE_XMMS",
            "CFI_RESTORE_STATE_AND_DEF_CFA rsp, 80",
            "jmp *%rdx",
        ],
    )
    if re.search(
        r"\.Losr_entry:\s*\n"
        r"\s*CFI_RESTORE_STATE_AND_DEF_CFA rsp, 256\s*\n"
        r"#if defined\(_WIN32\)\s*\n"
        r"\s*CFI_DEF_CFA_REGISTER\(r12\)\s*\n"
        r"#else\s*\n"
        r"\s*CFI_DEF_CFA_REGISTER\(rbp\)\s*\n"
        r"#endif",
        osr,
    ) is None:
        fail("OSR CFA register must remain R12 on Windows x64 and RBP on Linux")
    osr_return = source_region(quick, ".Losr_return:", ".seh_endproc")
    require_ordered(
        osr_return,
        "Windows x64 OSR return source",
        [
            ".seh_stackalloc 248",
            ".seh_savereg %r15, 8",
            ".seh_savexmm %xmm6, 64",
            ".seh_savexmm %xmm11, 144",
            ".seh_savexmm %xmm15, 208",
            ".seh_savereg %rbp, 240",
            ".seh_endprologue",
            "movq 8(%rsp), %r15",
            "movdqu 64(%rsp), %xmm6",
            "movdqu 144(%rsp), %xmm11",
            "movdqu 208(%rsp), %xmm15",
            "movq 240(%rsp), %rbp",
            "movq %rax, (%rcx)",
            "addq LITERAL(248), %rsp",
            "ret",
        ],
    )


def save_tokens() -> list[str]:
    return [
        "subq\t$0xa0, %rsp",
        "movdqu\t%xmm6, (%rsp)",
        "movdqu\t%xmm7, 0x10(%rsp)",
        "movdqu\t%xmm8, 0x20(%rsp)",
        "movdqu\t%xmm9, 0x30(%rsp)",
        "movdqu\t%xmm10, 0x40(%rsp)",
        "movdqu\t%xmm11, 0x50(%rsp)",
        "movdqu\t%xmm12, 0x60(%rsp)",
        "movdqu\t%xmm13, 0x70(%rsp)",
        "movdqu\t%xmm14, 0x80(%rsp)",
        "movdqu\t%xmm15, 0x90(%rsp)",
    ]


def restore_tokens() -> list[str]:
    return [
        "movdqu\t(%rsp), %xmm6",
        "movdqu\t0x10(%rsp), %xmm7",
        "movdqu\t0x20(%rsp), %xmm8",
        "movdqu\t0x30(%rsp), %xmm9",
        "movdqu\t0x40(%rsp), %xmm10",
        "movdqu\t0x50(%rsp), %xmm11",
        "movdqu\t0x60(%rsp), %xmm12",
        "movdqu\t0x70(%rsp), %xmm13",
        "movdqu\t0x80(%rsp), %xmm14",
        "movdqu\t0x90(%rsp), %xmm15",
        "addq\t$0xa0, %rsp",
    ]


def check_boundary_object(win_dis: str) -> None:
    for symbol in ("art_quick_invoke_stub", "art_quick_invoke_static_stub"):
        win_body = object_function(win_dis, symbol)
        require_ordered(
            win_body,
            f"Windows x64 {symbol} object",
            [
                "pushq\t%rdi",
                "pushq\t%rsi",
                "movq\t0x38(%rsp), %r10",
                "movq\t0x40(%rsp), %r11",
                *save_tokens(),
                "callq\t*0x18(%rdi)",
                "popq\t%rbp",
                *restore_tokens(),
                "popq\t%rsi",
                "popq\t%rdi",
            ],
        )
        if win_body.count("subq\t$0xa0, %rsp") != 1:
            fail(f"Windows x64 {symbol} must reserve exactly one XMM save area")
        if win_body.count("addq\t$0xa0, %rsp") != 1:
            fail(f"Windows x64 {symbol} must release exactly one XMM save area")

    symbol = "art_quick_osr_stub"
    win_body = object_function(win_dis, symbol)
    require_ordered(
        win_body,
        "Windows x64 art_quick_osr_stub object",
        [
            "movq\t0x28(%rsp), %r10",
            "movq\t0x30(%rsp), %r11",
            "pushq\t%rbp",
            "pushq\t%rdi",
            "pushq\t%rsi",
            *save_tokens(),
            "movq\t%rsp, %r12",
            "jmp\t",
            "subq\t%rcx, %rsp",
            "rep\t\tmovsb",
            "movq\t%rsp, %rbp",
            "jmpq\t*%rdx",
            "callq\t",
            "movq\t0x8(%rsp), %r15",
            "movq\t0x28(%rsp), %rbx",
            "movdqu\t0x40(%rsp), %xmm6",
            "movdqu\t0x90(%rsp), %xmm11",
            "movdqu\t0xd0(%rsp), %xmm15",
            "movq\t0xe0(%rsp), %rsi",
            "movq\t0xe8(%rsp), %rdi",
            "movq\t%rax, (%rcx)",
            "addq\t$0xf8, %rsp",
            "retq",
        ],
    )
    if win_body.count("subq\t$0xa0, %rsp") != 1:
        fail("Windows x64 art_quick_osr_stub must reserve exactly one XMM save area")
    if win_body.count("addq\t$0xf8, %rsp") != 1:
        fail("Windows x64 art_quick_osr_stub must have one RSP-based return epilogue")


def check_frame_variant(
    build: Path,
    variant: str,
    quick_object: Path,
    readobj: Path,
) -> None:
    if variant not in ("product", "win32-frame-attribution"):
        fail(f"W-003 structural gate does not admit build variant {variant!r}")
    instrumented = variant == "win32-frame-attribution"
    exports = run(readobj, "--coff-exports", str(build / "art.dll"))
    object_symbols = run(readobj, "--symbols", str(quick_object))
    for symbol in ("art_w003_frame_probe_reset", "art_w003_frame_probe_snapshot"):
        present = f"Name: {symbol}" in exports
        if present != instrumented:
            state = "missing from instrumented" if instrumented else "present in product"
            fail(f"{symbol} is {state} art.dll")
    for symbol in (
        "art_w003_frame_probe_refs_only",
        "art_w003_frame_probe_refs_and_args",
        "art_w003_frame_probe_all_callee_saves",
        "art_w003_frame_probe_everything",
    ):
        present = f"Name: {symbol}" in object_symbols
        if present != instrumented:
            state = "missing from instrumented" if instrumented else "present in product"
            fail(f"{symbol} is {state} quick object")


def check_xmm_probe(build: Path, readobj: Path, objdump: Path) -> None:
    dll = build / "tests/libw003xmmsentinel.dll"
    if not dll.is_file() or dll.is_symlink():
        fail(f"required XMM probe DLL is missing or linked: {dll}")
    exports = run(readobj, "--coff-exports", str(dll))
    if "Name: Java_W003XmmSentinelProbe_runXmmSentinel" not in exports:
        fail("W-003 XMM probe DLL is missing its JNI export")

    object_root = build / "tests/CMakeFiles/w003xmmsentinel.dir"
    assembly = find_one(object_root, "sentinel_x86_64.S.obj")
    disassembly = run(objdump, "-dr", "--no-show-raw-insn", str(assembly))
    for token in (
        "subq\t$0xc8, %rsp",
        "movdqu\t%xmm6, 0x20(%rsp)",
        "movdqu\t%xmm15, 0xb0(%rsp)",
        "IMAGE_REL_AMD64_REL32\tW003InvokeManagedCallback",
        "movdqu\t0x20(%rsp), %xmm6",
        "movdqu\t0xb0(%rsp), %xmm15",
        "addq\t$0xc8, %rsp",
    ):
        if token not in disassembly:
            fail(f"W-003 XMM assembly object is missing {token!r}")

    unwind = run(readobj, "--unwind", str(assembly))
    if "W003XmmSentinelAssembly" not in unwind:
        fail("W-003 XMM assembly unwind omits the normal sentinel")
    if "W003XmmExceptionSentinelAssembly" not in unwind:
        fail("W-003 XMM assembly unwind omits the exception sentinel")
    if unwind.count("SAVE_XMM128 reg=XMM") != 20:
        fail("W-003 XMM assembly does not describe exactly twenty XMM saves")
    if "SAVE_XMM128 reg=XMM15, offset=0xB0" not in unwind:
        fail("W-003 XMM assembly unwind omits the final XMM15 save")

    helper_object = find_one(object_root, "probe.c.obj")
    helper = object_function(
        run(objdump, "-dr", "--no-show-raw-insn", str(helper_object)),
        "W003InvokeManagedCallback",
    )
    if re.search(r"%xmm(?:6|7|8|9|10|11|12|13|14|15)\b", helper):
        fail("W-003 C callback masks the boundary with local nonvolatile XMM saves")
    if "callq\t*0x408(%rax)" not in helper:
        fail("W-003 C callback does not call the JNI CallStaticIntMethod slot")


def main() -> int:
    repo = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--llvm-readobj", type=Path, required=True)
    parser.add_argument("--llvm-objdump", type=Path, required=True)
    args = parser.parse_args()
    build = args.build.resolve()
    if not (build / "art.dll").is_file():
        fail(f"required Windows x64 artifact is missing: {build / 'art.dll'}")
    readobj = require_tool(args.llvm_readobj)
    objdump = require_tool(args.llvm_objdump)

    art = repo / "vendor/art"
    quick = (art / "runtime/arch/x86_64/quick_entrypoints_x86_64.S").read_text(
        encoding="utf-8"
    )
    support = (art / "runtime/arch/x86_64/asm_support_x86_64.S").read_text(
        encoding="utf-8"
    )
    check_setup_source(quick, support)
    check_boundary_source(quick)

    win_obj = find_one(build / "CMakeFiles/art.dir", "quick_entrypoints_x86_64.S.obj")
    win_dis = run(objdump, "-dr", "--no-show-raw-insn", str(win_obj))
    check_boundary_object(win_dis)
    check_frame_variant(build, args.variant, win_obj, readobj)
    check_xmm_probe(build, readobj, objdump)

    win_traps = trap_distribution(win_dis)
    if not win_traps:
        fail("Windows x64 quick disassembly yielded no function-attributed traps")

    print(
        "W-003 quick-boundary structural check: PASS "
        f"(variant={args.variant} boundaries={len(BOUNDARY_SYMBOLS)} "
        f"trap_functions={len(win_traps)} "
        f"traps={sum(win_traps.values())} xmm_saves=20)"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        print(f"W-003 quick-boundary structural check: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
