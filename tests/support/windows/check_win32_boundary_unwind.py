#!/usr/bin/env python3
"""Audit PE unwind metadata for unified ART native/managed boundary stubs."""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys


FULL_XMM_UNWIND = tuple(
    f"SAVE_XMM128 reg=XMM{register}, offset=0x{offset:X}"
    for register, offset in zip(range(6, 16), range(0x40, 0xE0, 0x10))
)

BOUNDARIES = {
    "ExecuteSwitchImplAsm": (
        "FrameRegister: -",
        "ALLOC_SMALL size=32",
        "PUSH_NONVOL reg=RBX",
    ),
    "art_quick_invoke_stub": (
        "FrameRegister: RBP",
        "ALLOC_LARGE size=160",
        "PUSH_NONVOL reg=RDI",
        "PUSH_NONVOL reg=RSI",
        "PUSH_NONVOL reg=RBP",
        "PUSH_NONVOL reg=RBX",
        "PUSH_NONVOL reg=R12",
        "PUSH_NONVOL reg=R13",
        "PUSH_NONVOL reg=R14",
        "PUSH_NONVOL reg=R15",
        *FULL_XMM_UNWIND,
    ),
    "art_quick_invoke_static_stub": (
        "FrameRegister: RBP",
        "ALLOC_LARGE size=160",
        "PUSH_NONVOL reg=RDI",
        "PUSH_NONVOL reg=RSI",
        "PUSH_NONVOL reg=RBP",
        "PUSH_NONVOL reg=RBX",
        "PUSH_NONVOL reg=R12",
        "PUSH_NONVOL reg=R13",
        "PUSH_NONVOL reg=R14",
        "PUSH_NONVOL reg=R15",
        *FULL_XMM_UNWIND,
    ),
    "art_quick_osr_stub": (
        "FrameRegister: R12",
        "FrameOffset: 0x0",
        "SET_FPREG reg=R12, offset=0x0",
        "ALLOC_LARGE size=160",
        "PUSH_NONVOL reg=RDI",
        "PUSH_NONVOL reg=RSI",
        "PUSH_NONVOL reg=RBP",
        "PUSH_NONVOL reg=RBX",
        "PUSH_NONVOL reg=R12",
        "PUSH_NONVOL reg=R13",
        "PUSH_NONVOL reg=R14",
        "PUSH_NONVOL reg=R15",
        *FULL_XMM_UNWIND,
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
        "SAVE_NONVOL reg=RDI, offset=0x1400",
    ),
    "art_quick_to_interpreter_bridge": (
        "FrameRegister: -",
        "ALLOC_SMALL size=112",
        "PUSH_NONVOL reg=RSI",
        "PUSH_NONVOL reg=RBP",
        "PUSH_NONVOL reg=RBX",
        "PUSH_NONVOL reg=R12",
        "PUSH_NONVOL reg=R13",
        "PUSH_NONVOL reg=R14",
        "PUSH_NONVOL reg=R15",
    ),
}

NTERP_ADAPTER_START = "NterpWindowsInvokeAdapterStart"
NTERP_ADAPTER_END = "NterpWindowsInvokeAdapterEnd"
NTERP_ADAPTER_COUNT = 187


def run_readobj(readobj: pathlib.Path, option: str, dll: pathlib.Path) -> str:
    return subprocess.check_output(
        [str(readobj), option, str(dll)], text=True, errors="replace"
    )


def parse_section_virtual_addresses(output: str) -> dict[int, int]:
    found: dict[int, int] = {}
    pattern = re.compile(
        r"^\s*SECTION HEADER #(\d+)\s*$.*?"
        r"^\s*([0-9A-Fa-f]+) virtual address\s*$",
        re.MULTILINE | re.DOTALL,
    )
    for match in pattern.finditer(output):
        found[int(match.group(1), 10)] = int(match.group(2), 16)
    if not found:
        raise RuntimeError("PDB image section headers are missing")
    return found


def parse_public_symbol_locations(
    output: str, required: set[str] | None = None
) -> dict[str, tuple[int, int]]:
    if required is None:
        required = set(BOUNDARIES)
    found: dict[str, tuple[int, int]] = {}
    name: str | None = None
    for line in output.splitlines():
        name_match = re.search(r"`([^`]*)`\s*$", line)
        if name_match is not None:
            candidate = name_match.group(1)
            name = candidate if candidate in required else None
            continue
        address_match = re.search(r"addr = (\d+):(\d+)\s*$", line)
        if address_match is not None and name is not None:
            location = (
                int(address_match.group(1), 10),
                int(address_match.group(2), 10),
            )
            previous = found.setdefault(name, location)
            if previous != location:
                raise RuntimeError(
                    f"PDB boundary symbol has conflicting addresses: {name}"
                )
            name = None
    missing = sorted(required - set(found))
    if missing:
        raise RuntimeError(f"missing private PDB boundary symbols: {', '.join(missing)}")
    return found


def pdb_symbol_rvas(
    pdbutil: pathlib.Path, pdb: pathlib.Path, required: set[str] | None = None
) -> dict[str, int]:
    output = subprocess.check_output(
        [str(pdbutil), "dump", "--publics", "--section-headers", str(pdb)],
        text=True,
        errors="replace",
    )
    sections = parse_section_virtual_addresses(output)
    locations = parse_public_symbol_locations(output, required)
    found: dict[str, int] = {}
    for name, (section, offset) in locations.items():
        if section not in sections:
            raise RuntimeError(f"{name}: PDB section {section} has no image header")
        found[name] = sections[section] + offset
    return found


def image_base(readobj: pathlib.Path, dll: pathlib.Path) -> int:
    output = run_readobj(readobj, "--file-headers", dll)
    match = re.search(r"^\s*ImageBase:\s*(0x[0-9A-Fa-f]+)\s*$", output, re.MULTILINE)
    if match is None:
        raise RuntimeError("PE image base is missing")
    return int(match.group(1), 16)


def unwind_records(
    readobj: pathlib.Path,
    dll: pathlib.Path,
    addresses: set[int],
    address_range: tuple[int, int] | None = None,
) -> dict[int, str]:
    process = subprocess.Popen(
        [str(readobj), "--unwind", str(dll)],
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
        in_range = (
            start is not None
            and address_range is not None
            and address_range[0] <= start < address_range[1]
        )
        if start in addresses or in_range:
            assert start is not None
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
    parser.add_argument("--art-pdb", type=pathlib.Path, required=True)
    parser.add_argument("--llvm-readobj", type=pathlib.Path, required=True)
    parser.add_argument("--llvm-pdbutil", type=pathlib.Path, required=True)
    args = parser.parse_args()

    dll = args.art_dll.resolve()
    pdb = args.art_pdb.resolve()
    if not dll.is_file():
        print(f"missing art.dll: {dll}", file=sys.stderr)
        return 1
    if not pdb.is_file():
        print(f"missing art.pdb: {pdb}", file=sys.stderr)
        return 1
    readobj = args.llvm_readobj.resolve()
    pdbutil = args.llvm_pdbutil.resolve()
    for name, tool in (("llvm-readobj", readobj), ("llvm-pdbutil", pdbutil)):
        if not tool.is_file():
            print(f"{name} is required: {tool}", file=sys.stderr)
            return 1

    try:
        public_symbols = set(BOUNDARIES) | {
            NTERP_ADAPTER_START,
            NTERP_ADAPTER_END,
        }
        rvas = pdb_symbol_rvas(pdbutil, pdb, public_symbols)
        base = image_base(readobj, dll)
        addresses = {base + rvas[name] for name in BOUNDARIES}
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

        adapter_start = base + rvas[NTERP_ADAPTER_START]
        adapter_end = base + rvas[NTERP_ADAPTER_END]
        adapter_records = unwind_records(
            readobj,
            dll,
            set(),
            address_range=(adapter_start, adapter_end),
        )
        ordered_adapters = sorted(adapter_records.items())
        if len(ordered_adapters) != NTERP_ADAPTER_COUNT:
            errors.append(
                "nterp invoke adapters: expected "
                f"{NTERP_ADAPTER_COUNT} unwind records, got {len(ordered_adapters)}"
            )
        for index, (address, record) in enumerate(ordered_adapters):
            if index >= NTERP_ADAPTER_COUNT:
                break
            gap = 8 + 16 * index
            allocation = gap + 80
            required = (
                "PrologSize: 0",
                "FrameRegister: -",
                f"ALLOC_{'SMALL' if allocation <= 128 else 'LARGE'} size={allocation}",
                f"SAVE_NONVOL reg=RBX, offset=0x{gap + 32:X}",
                f"SAVE_NONVOL reg=RBP, offset=0x{gap + 40:X}",
                f"SAVE_NONVOL reg=R12, offset=0x{gap + 48:X}",
                f"SAVE_NONVOL reg=R13, offset=0x{gap + 56:X}",
                f"SAVE_NONVOL reg=R14, offset=0x{gap + 64:X}",
                f"SAVE_NONVOL reg=R15, offset=0x{gap + 72:X}",
            )
            for marker in required:
                if marker not in record:
                    errors.append(f"nterp invoke adapter {index}: missing {marker}")
            expected_start = adapter_start if index == 0 else None
            if expected_start is not None and address != expected_start:
                errors.append(
                    "nterp invoke adapters: first unwind record does not start at "
                    "NterpWindowsInvokeAdapterStart"
                )
            end_match = re.search(
                r"EndAddress:\s*\((0x[0-9A-Fa-f]+)\)", record
            )
            if end_match is None:
                errors.append(f"nterp invoke adapter {index}: missing end address")
            else:
                expected_end = (
                    ordered_adapters[index + 1][0]
                    if index + 1 < len(ordered_adapters)
                    else adapter_end
                )
                if int(end_match.group(1), 16) != expected_end:
                    errors.append(
                        f"nterp invoke adapter {index}: unwind range is not contiguous"
                    )
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
                    "ALLOC_LARGE size=248",
                    "SAVE_NONVOL reg=R15, offset=0x8",
                    "SAVE_NONVOL reg=R14, offset=0x10",
                    "SAVE_NONVOL reg=R13, offset=0x18",
                    "SAVE_NONVOL reg=R12, offset=0x20",
                    "SAVE_NONVOL reg=RBX, offset=0x28",
                    *FULL_XMM_UNWIND,
                    "SAVE_NONVOL reg=RSI, offset=0xE0",
                    "SAVE_NONVOL reg=RDI, offset=0xE8",
                    "SAVE_NONVOL reg=RBP, offset=0xF0",
                )
                for marker in return_required:
                    if marker not in return_record:
                        errors.append(f"art_quick_osr_return: missing {marker}")

        bridge_address = base + rvas["art_quick_to_interpreter_bridge"]
        bridge_record = records.get(bridge_address, "")
        if bridge_record.count("ALLOC_SMALL size=8") != 4:
            errors.append(
                "art_quick_to_interpreter_bridge: expected four volatile push slots"
            )
        bridge_end_match = re.search(
            r"EndAddress:\s*\((0x[0-9A-Fa-f]+)\)", bridge_record
        )
        if bridge_end_match is None:
            errors.append("art_quick_to_interpreter_bridge: missing end address")
        else:
            pending_address = int(bridge_end_match.group(1), 16)
            pending_record = unwind_records(readobj, dll, {pending_address}).get(
                pending_address
            )
            if pending_record is None:
                errors.append(
                    "art_quick_to_interpreter_bridge: missing contiguous pending range"
                )
            else:
                pending_required = (
                    "FrameRegister: -",
                    "ALLOC_SMALL size=40",
                    "PUSH_NONVOL reg=RBX",
                    "PUSH_NONVOL reg=RBP",
                    "PUSH_NONVOL reg=R12",
                    "PUSH_NONVOL reg=R13",
                    "PUSH_NONVOL reg=R14",
                    "PUSH_NONVOL reg=R15",
                )
                for marker in pending_required:
                    if marker not in pending_record:
                        errors.append(
                            f"art_quick_to_interpreter_pending: missing {marker}"
                        )
        if errors:
            print("Windows x64 boundary unwind audit failed:", file=sys.stderr)
            for error in errors:
                print(f"  {error}", file=sys.stderr)
            return 1
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as error:
        print(f"Windows x64 boundary unwind audit failed: {error}", file=sys.stderr)
        return 1

    print(
        "win32_boundary_unwind OK "
        + " ".join(f"{name}=0x{rvas[name]:x}" for name in BOUNDARIES)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
