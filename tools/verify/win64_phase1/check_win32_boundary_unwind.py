#!/usr/bin/env python3
"""Audit PE unwind metadata for Win64 ART native/managed boundary stubs."""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import subprocess
import sys


BOUNDARIES = {
    "art_quick_invoke_stub": (
        "FrameRegister: RBP",
        "ALLOC_SMALL size=96",
        "PUSH_NONVOL reg=RDI",
        "PUSH_NONVOL reg=RSI",
        "PUSH_NONVOL reg=RBP",
        "PUSH_NONVOL reg=RBX",
        "PUSH_NONVOL reg=R12",
        "PUSH_NONVOL reg=R13",
        "PUSH_NONVOL reg=R14",
        "PUSH_NONVOL reg=R15",
        "SAVE_XMM128 reg=XMM6, offset=0x40",
        "SAVE_XMM128 reg=XMM7, offset=0x50",
        "SAVE_XMM128 reg=XMM8, offset=0x60",
        "SAVE_XMM128 reg=XMM9, offset=0x70",
        "SAVE_XMM128 reg=XMM10, offset=0x80",
        "SAVE_XMM128 reg=XMM11, offset=0x90",
    ),
    "art_quick_invoke_static_stub": (
        "FrameRegister: RBP",
        "ALLOC_SMALL size=96",
        "PUSH_NONVOL reg=RDI",
        "PUSH_NONVOL reg=RSI",
        "PUSH_NONVOL reg=RBP",
        "PUSH_NONVOL reg=RBX",
        "PUSH_NONVOL reg=R12",
        "PUSH_NONVOL reg=R13",
        "PUSH_NONVOL reg=R14",
        "PUSH_NONVOL reg=R15",
        "SAVE_XMM128 reg=XMM6, offset=0x40",
        "SAVE_XMM128 reg=XMM7, offset=0x50",
        "SAVE_XMM128 reg=XMM8, offset=0x60",
        "SAVE_XMM128 reg=XMM9, offset=0x70",
        "SAVE_XMM128 reg=XMM10, offset=0x80",
        "SAVE_XMM128 reg=XMM11, offset=0x90",
    ),
    "art_quick_osr_stub": (
        "FrameRegister: RBP",
        "FrameOffset: 0x0",
        "SET_FPREG reg=RBP, offset=0x0",
        "ALLOC_SMALL size=96",
        "PUSH_NONVOL reg=RDI",
        "PUSH_NONVOL reg=RSI",
        "PUSH_NONVOL reg=RBP",
        "PUSH_NONVOL reg=RBX",
        "PUSH_NONVOL reg=R12",
        "PUSH_NONVOL reg=R13",
        "PUSH_NONVOL reg=R14",
        "PUSH_NONVOL reg=R15",
        "SAVE_XMM128 reg=XMM6, offset=0x40",
        "SAVE_XMM128 reg=XMM7, offset=0x50",
        "SAVE_XMM128 reg=XMM8, offset=0x60",
        "SAVE_XMM128 reg=XMM9, offset=0x70",
        "SAVE_XMM128 reg=XMM10, offset=0x80",
        "SAVE_XMM128 reg=XMM11, offset=0x90",
    ),
    "art_quick_generic_jni_trampoline": (
        "FrameRegister: R12",
        "ALLOC_LARGE size=5120",
        "PUSH_NONVOL reg=R12",
        "PUSH_NONVOL reg=R13",
        "PUSH_NONVOL reg=R14",
        "PUSH_NONVOL reg=R15",
        "PUSH_NONVOL reg=RSI",
        "PUSH_NONVOL reg=RBP",
        "PUSH_NONVOL reg=RBX",
        "SAVE_NONVOL reg=RDI",
    ),
}


def run_readobj(readobj: str, option: str, dll: pathlib.Path) -> str:
    return subprocess.check_output(
        [readobj, option, str(dll)], text=True, errors="replace"
    )


def exported_rvas(readobj: str, dll: pathlib.Path) -> dict[str, int]:
    output = run_readobj(readobj, "--coff-exports", dll)
    found: dict[str, int] = {}
    name: str | None = None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("Name: "):
            name = stripped.removeprefix("Name: ")
        elif stripped.startswith("RVA: ") and name in BOUNDARIES:
            found[name] = int(stripped.removeprefix("RVA: "), 16)
            name = None
    missing = sorted(set(BOUNDARIES) - set(found))
    if missing:
        raise RuntimeError(f"missing boundary exports: {', '.join(missing)}")
    return found


def image_base(readobj: str, dll: pathlib.Path) -> int:
    output = run_readobj(readobj, "--file-headers", dll)
    match = re.search(r"^\s*ImageBase:\s*(0x[0-9A-Fa-f]+)\s*$", output, re.MULTILINE)
    if match is None:
        raise RuntimeError("PE image base is missing")
    return int(match.group(1), 16)


def unwind_records(
    readobj: str, dll: pathlib.Path, addresses: set[int]
) -> dict[int, str]:
    process = subprocess.Popen(
        [readobj, "--unwind", str(dll)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
    )
    assert process.stdout is not None
    records: dict[int, str] = {}
    block: list[str] = []
    start: int | None = None

    def finish_block() -> None:
        if start in addresses:
            records[start] = "".join(block)

    for line in process.stdout:
        if line.strip() == "RuntimeFunction {":
            finish_block()
            block = [line]
            start = None
            continue
        if block:
            block.append(line)
            match = re.search(r"StartAddress:\s*\((0x[0-9A-Fa-f]+)\)", line)
            if match is not None:
                start = int(match.group(1), 16)
    finish_block()

    stderr = process.stderr.read() if process.stderr is not None else ""
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(
            f"llvm-readobj --unwind failed with {return_code}: {stderr.strip()}"
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--art-dll", type=pathlib.Path, required=True)
    args = parser.parse_args()

    dll = args.art_dll.resolve()
    if not dll.is_file():
        print(f"missing art.dll: {dll}", file=sys.stderr)
        return 1
    readobj = shutil.which("llvm-readobj")
    if readobj is None:
        print("llvm-readobj is required", file=sys.stderr)
        return 1

    try:
        rvas = exported_rvas(readobj, dll)
        base = image_base(readobj, dll)
        addresses = {base + rva for rva in rvas.values()}
        records = unwind_records(readobj, dll, addresses)
        errors: list[str] = []
        for name, required in BOUNDARIES.items():
            address = base + rvas[name]
            record = records.get(address)
            if record is None:
                errors.append(f"{name}: no runtime-function entry at 0x{address:x}")
                continue
            prolog = re.search(r"PrologSize:\s*(\d+)", record)
            if prolog is None or int(prolog.group(1)) > 255:
                errors.append(f"{name}: invalid PE prologue size")
            for marker in required:
                if marker not in record:
                    errors.append(f"{name}: missing {marker}")
        osr_address = base + rvas["art_quick_osr_stub"]
        osr_record = records.get(osr_address, "")
        osr_end_match = re.search(
            r"EndAddress:\s*\((0x[0-9A-Fa-f]+)\)", osr_record
        )
        if osr_end_match is None:
            errors.append("art_quick_osr_stub: missing end address")
        else:
            return_address = int(osr_end_match.group(1), 16)
            return_record = unwind_records(readobj, dll, {return_address}).get(
                return_address
            )
            if return_record is None:
                errors.append("art_quick_osr_stub: missing contiguous return unwind range")
            else:
                return_required = (
                    "PrologSize: 0",
                    "FrameRegister: -",
                    "ALLOC_LARGE size=184",
                    "SAVE_NONVOL reg=R15, offset=0x8",
                    "SAVE_NONVOL reg=R14, offset=0x10",
                    "SAVE_NONVOL reg=R13, offset=0x18",
                    "SAVE_NONVOL reg=R12, offset=0x20",
                    "SAVE_NONVOL reg=RBX, offset=0x28",
                    "SAVE_XMM128 reg=XMM6, offset=0x40",
                    "SAVE_XMM128 reg=XMM11, offset=0x90",
                    "SAVE_NONVOL reg=RSI, offset=0xA0",
                    "SAVE_NONVOL reg=RDI, offset=0xA8",
                    "SAVE_NONVOL reg=RBP, offset=0xB0",
                )
                for marker in return_required:
                    if marker not in return_record:
                        errors.append(f"art_quick_osr_return: missing {marker}")
        if errors:
            print("Win64 boundary unwind audit failed:", file=sys.stderr)
            for error in errors:
                print(f"  {error}", file=sys.stderr)
            return 1
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as error:
        print(f"Win64 boundary unwind audit failed: {error}", file=sys.stderr)
        return 1

    print(
        "win32_boundary_unwind OK "
        + " ".join(f"{name}=0x{rvas[name]:x}" for name in BOUNDARIES)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
