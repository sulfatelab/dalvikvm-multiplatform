#!/usr/bin/env python3
"""Verify W-003 quick-frame traps and Microsoft XMM boundary preservation."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re
import shutil
import subprocess
import sys


BOUNDARY_SYMBOLS = (
    "art_quick_invoke_stub",
    "art_quick_invoke_static_stub",
    "art_quick_osr_stub",
)


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
    save = source_region(quick, "MACRO0(SAVE_WIN64_NATIVE_XMMS)", "END_MACRO")
    restore = source_region(
        quick, "MACRO0(RESTORE_WIN64_NATIVE_XMMS)", "END_MACRO"
    )
    require_ordered(
        save,
        "Win64 XMM save macro",
        [
            "#if defined(_WIN32)",
            "subq LITERAL(96), %rsp",
            "movdqu %xmm6, 0(%rsp)",
            "movdqu %xmm7, 16(%rsp)",
            "movdqu %xmm8, 32(%rsp)",
            "movdqu %xmm9, 48(%rsp)",
            "movdqu %xmm10, 64(%rsp)",
            "movdqu %xmm11, 80(%rsp)",
            "#endif",
        ],
    )
    require_ordered(
        restore,
        "Win64 XMM restore macro",
        [
            "#if defined(_WIN32)",
            "movdqu 0(%rsp), %xmm6",
            "movdqu 16(%rsp), %xmm7",
            "movdqu 32(%rsp), %xmm8",
            "movdqu 48(%rsp), %xmm9",
            "movdqu 64(%rsp), %xmm10",
            "movdqu 80(%rsp), %xmm11",
            "addq LITERAL(96), %rsp",
            "#endif",
        ],
    )
    if quick.count("    SAVE_WIN64_NATIVE_XMMS\n") != 3:
        fail("expected exactly three Win64 native XMM save sites")
    if quick.count("    RESTORE_WIN64_NATIVE_XMMS\n") != 3:
        fail("expected exactly three Win64 native XMM restore sites")

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
                "SAVE_WIN64_NATIVE_XMMS",
                f"LOOP_OVER_SHORTY_LOADING_XMMS xmm6, {xmm_label}",
                f"{gpr_label}:",
                "call *ART_METHOD_QUICK_CODE_OFFSET_64(%rdi)",
                "POP rbp",
                "RESTORE_WIN64_NATIVE_XMMS",
                "popq %rsi",
                "popq %rdi",
            ],
        )

    osr = source_function(quick, "art_quick_osr_stub")
    require_ordered(
        osr,
        "art_quick_osr_stub source",
        [
            "PUSH rdi",
            "PUSH rsi",
            "movq 0x38(%rsp), %r10",
            "movq 0x40(%rsp), %r11",
            "SAVE_WIN64_NATIVE_XMMS",
            "PUSH r15",
            "call .Losr_entry",
            "POP r15",
            "POP rbp",
            "RESTORE_WIN64_NATIVE_XMMS",
            "POP rsi",
            "POP rdi",
            "ret",
            ".Losr_entry:",
            "CFI_RESTORE_STATE_AND_DEF_CFA rsp, 192",
            "#else",
            "CFI_RESTORE_STATE_AND_DEF_CFA rsp, 80",
            "jmp *%rdx",
        ],
    )


def save_tokens() -> list[str]:
    return [
        "subq\t$0x60, %rsp",
        "movdqu\t%xmm6, (%rsp)",
        "movdqu\t%xmm7, 0x10(%rsp)",
        "movdqu\t%xmm8, 0x20(%rsp)",
        "movdqu\t%xmm9, 0x30(%rsp)",
        "movdqu\t%xmm10, 0x40(%rsp)",
        "movdqu\t%xmm11, 0x50(%rsp)",
    ]


def restore_tokens() -> list[str]:
    return [
        "movdqu\t(%rsp), %xmm6",
        "movdqu\t0x10(%rsp), %xmm7",
        "movdqu\t0x20(%rsp), %xmm8",
        "movdqu\t0x30(%rsp), %xmm9",
        "movdqu\t0x40(%rsp), %xmm10",
        "movdqu\t0x50(%rsp), %xmm11",
        "addq\t$0x60, %rsp",
    ]


def check_boundary_objects(win_dis: str, linux_dis: str) -> None:
    for symbol in BOUNDARY_SYMBOLS:
        win_body = object_function(win_dis, symbol)
        linux_body = object_function(linux_dis, symbol)
        call_token = (
            "callq\t*0x18(%rdi)"
            if symbol != "art_quick_osr_stub"
            else "callq\t"
        )
        require_ordered(
            win_body,
            f"Win64 {symbol} object",
            [
                "pushq\t%rdi",
                "pushq\t%rsi",
                "movq\t0x38(%rsp), %r10",
                "movq\t0x40(%rsp), %r11",
                *save_tokens(),
                call_token,
                "popq\t%rbp",
                *restore_tokens(),
                "popq\t%rsi",
                "popq\t%rdi",
            ],
        )
        if win_body.count("subq\t$0x60, %rsp") != 1:
            fail(f"Win64 {symbol} must reserve exactly one XMM save area")
        if win_body.count("addq\t$0x60, %rsp") != 1:
            fail(f"Win64 {symbol} must release exactly one XMM save area")
        if "movdqu" in linux_body:
            fail(f"Linux {symbol} unexpectedly gained Win64 XMM boundary saves")
        if "subq\t$0x60, %rsp" in linux_body:
            fail(f"Linux {symbol} unexpectedly reserves the Win64 save area")


def main() -> int:
    repo = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--win-build",
        type=Path,
        default=repo / "build/win64_phase1",
        help="configured Win64 build directory",
    )
    parser.add_argument(
        "--linux-build",
        type=Path,
        default=repo / "build/native",
        help="configured Linux build directory",
    )
    args = parser.parse_args()
    win_build = args.win_build.resolve()
    linux_build = args.linux_build.resolve()
    if not (win_build / "art.dll").is_file():
        fail(f"required Win64 artifact is missing: {win_build / 'art.dll'}")
    if not (linux_build / "libart.so").is_file():
        fail(f"required Linux artifact is missing: {linux_build / 'libart.so'}")

    art = repo / "vendor/art"
    quick = (art / "runtime/arch/x86_64/quick_entrypoints_x86_64.S").read_text(
        encoding="utf-8"
    )
    support = (art / "runtime/arch/x86_64/asm_support_x86_64.S").read_text(
        encoding="utf-8"
    )
    check_setup_source(quick, support)
    check_boundary_source(quick)

    objdump = require_tool("llvm-objdump")
    win_obj = find_one(
        win_build / "CMakeFiles/art.dir", "quick_entrypoints_x86_64.S.obj"
    )
    linux_obj = find_one(
        linux_build / "CMakeFiles/art.dir", "quick_entrypoints_x86_64.S.o"
    )
    win_dis = run(objdump, "-dr", "--no-show-raw-insn", str(win_obj))
    linux_dis = run(objdump, "-dr", "--no-show-raw-insn", str(linux_obj))
    check_boundary_objects(win_dis, linux_dis)

    win_traps = trap_distribution(win_dis)
    linux_traps = trap_distribution(linux_dis)
    if win_traps != linux_traps:
        only_win = win_traps - linux_traps
        only_linux = linux_traps - win_traps
        fail(
            "matched PE/ELF int3 distributions differ: "
            f"extra Win64={dict(only_win)}, extra Linux={dict(only_linux)}"
        )

    print(
        "W-003 quick-boundary structural check: PASS "
        f"(boundaries={len(BOUNDARY_SYMBOLS)} trap_functions={len(win_traps)} "
        f"traps={sum(win_traps.values())})"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        print(f"W-003 quick-boundary structural check: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
