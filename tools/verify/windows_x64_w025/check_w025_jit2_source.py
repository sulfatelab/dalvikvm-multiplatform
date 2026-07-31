#!/usr/bin/env python3
"""Check the static W-025 JIT-2 mapping and probe contract."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys


def fail(message: str) -> None:
    raise RuntimeError(message)


def require(text: str, source: str, *markers: str) -> None:
    for marker in markers:
        if marker not in text:
            fail(f"{source} is missing required contract text: {marker}")


def run(*command: str) -> str:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode != 0:
        fail(f"command failed ({result.returncode}): {' '.join(command)}\n"
             f"{result.stdout}{result.stderr}")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    build = args.build.resolve()

    mem_map = (repo / "vendor/art/libartbase/base/mem_map_windows.cc").read_text()
    jit_region = (repo / "vendor/art/runtime/jit/jit_memory_region.cc").read_text()
    section_probe_source = (
        repo / "tests/cases/jit-section-policy/probe.cc"
    ).read_text()
    create_match = re.search(
        r"void\* MemMap::CreatePageFileSection\(.*?\n\}", mem_map, re.DOTALL
    )
    if create_match is None:
        fail("CreatePageFileSection definition is missing")
    create = create_match.group(0)
    require(
        create,
        "CreatePageFileSection",
        "CreateFileMappingW(",
        "INVALID_HANDLE_VALUE",
        "PAGE_EXECUTE_READWRITE",
        "nullptr);",
    )
    for forbidden in ("CreateFileW(", "CreateFileA(", "GetTempPath", "mkstemp"):
        if forbidden in create:
            fail(f"CreatePageFileSection contains filesystem operation {forbidden}")

    require(
        jit_region,
        "JitMemoryRegion::Initialize",
        "MemMap::CreatePageFileSection(capacity",
        "kProtRX,",
        "/*low_4gb=*/true",
        "kProtRW,",
        "CHECK_EQ(primary.End(), exec.Begin())",
        "CheckJitSectionView(primary, primary.Begin(), PAGE_READONLY)",
        "CheckJitSectionView(exec, primary.Begin(), PAGE_EXECUTE_READ)",
        "CheckJitSectionView(writable, writable.Begin(), PAGE_READWRITE)",
        "CheckJitSectionView(non_exec, writable.Begin(), PAGE_READWRITE)",
    )
    require(
        section_probe_source,
        "W025SectionPolicyProbe",
        "free_end - reserve_begin",
        "ReserveExact(reserve_begin, reserve_size, reservations)",
    )
    if "kReserveChunk" in section_probe_source:
        fail("W025SectionPolicyProbe fragments free spans into slow scan chunks")

    section_probe = build / "W025SectionPolicyProbe.exe"
    mapping_probe = build / "libw025jitmappingprobe.dll"
    launcher = build / "W025PolicyLauncher.exe"
    for path in (section_probe, mapping_probe, launcher, build / "art.dll"):
        if not path.is_file():
            fail(f"required Windows artifact is missing: {path}")

    load_config = run("llvm-readobj", "--coff-load-config", str(section_probe))
    require(
        load_config,
        "W025SectionPolicyProbe load config",
        "CF_INSTRUMENTED",
        "CF_FUNCTION_TABLE_PRESENT",
    )
    imports = run("llvm-readobj", "--coff-imports", str(section_probe))
    for symbol in ("CreateFileMappingW", "MapViewOfFile3", "K32GetMappedFileNameW"):
        if f"Symbol: {symbol}" not in imports:
            fail(f"section probe does not import {symbol}")

    print("status=PASS")
    print("pagefile_section=INVALID_HANDLE_VALUE")
    print("section_name=unnamed")
    print("primary_view=low_R_RX")
    print("alias_view=unrestricted_RW_RW")
    print("source_filesystem_calls=0")
    print("probe_cfg_instrumented=1")
    print("probe_cfg_function_table=1")
    print("native_policy_launcher=present")
    print("runtime_mapping_probe=present")
    print("low_va_full_span_reservations=1")
    print("W025_JIT2_SOURCE_CHECK_PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError) as error:
        print(f"W025_JIT2_SOURCE_CHECK_FAIL: {error}", file=sys.stderr)
        sys.exit(1)
