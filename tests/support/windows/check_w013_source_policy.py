#!/usr/bin/env python3
"""Verify W-013 virtual-memory, mspace, and low-address source policy."""

from __future__ import annotations

import re
from pathlib import Path
import sys


EXPECTED_LOW_ADDRESS_FILES = {
    "runtime/gc/heap.cc",
    "runtime/gc/space/bump_pointer_space.cc",
    "runtime/gc/space/image_space.cc",
    "runtime/gc/space/large_object_space.cc",
    "runtime/gc/space/malloc_space.cc",
    "runtime/gc/space/region_space.cc",
    "runtime/jit/jit_memory_region.cc",
    "runtime/runtime.cc",
}


def fail(message: str) -> None:
    raise RuntimeError(message)


def read(repo: Path, relative: str) -> str:
    path = repo / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        fail(f"cannot read {relative}: {error}")


def require_pattern(text: str, pattern: str, label: str) -> None:
    if re.search(pattern, text, re.MULTILINE) is None:
        fail(f"missing {label}")


def reject_pattern(text: str, pattern: str, label: str) -> None:
    if re.search(pattern, text, re.MULTILINE) is not None:
        fail(f"forbidden {label}")


def check_repository(repo: Path) -> dict[str, int]:
    art = repo / "vendor/art"
    windows_map = read(repo, "vendor/art/libartbase/base/mem_map_windows.cc")
    mem_map_header = read(repo, "vendor/art/libartbase/base/mem_map.h")

    for pattern in (
        r"Walk free regions",
        r"Fallback: let the OS pick",
        r"want_low_4gb.*start == nullptr",
    ):
        reject_pattern(windows_map, pattern, f"manual/fallback low-address policy: {pattern}")
    for token in (
        "VirtualAlloc2",
        "MEM_ADDRESS_REQUIREMENTS",
        "AcquireWindowsMapOwner",
        "DiscardVirtualMemory",
    ):
        if token not in windows_map:
            fail(f"missing Windows MemMap contract token: {token}")
    for token in ("ActivateRange", "DeactivateRange", "DiscardRange"):
        if token not in mem_map_header:
            fail(f"missing MemMap::{token}")

    transition_files = (
        "vendor/art/runtime/gc/space/malloc_space.cc",
        "vendor/art/runtime/gc/space/dlmalloc_space.cc",
        "vendor/art/runtime/gc/space/rosalloc_space.cc",
        "vendor/art/runtime/gc/allocator/rosalloc.cc",
    )
    for relative in transition_files:
        reject_pattern(
            read(repo, relative),
            r"\b(?:mprotect|madvise)\s*\(",
            f"direct page transition in {relative}",
        )

    dlmalloc_space = read(repo, "vendor/art/runtime/gc/space/dlmalloc_space.cc")
    jit_region = read(repo, "vendor/art/runtime/jit/jit_memory_region.cc")
    if "lock_.AssertHeld" not in dlmalloc_space:
        fail("heap mspace external-lock assertion is missing")
    if "Locks::jit_lock_->AssertHeld" not in jit_region:
        fail("JIT mspace external-lock assertion is missing")

    runtime = read(repo, "vendor/art/runtime/runtime.cc")
    card_table_cc = read(repo, "vendor/art/runtime/gc/accounting/card_table.cc")
    card_table_h = read(repo, "vendor/art/runtime/gc/accounting/card_table.h")
    heap_inl = read(repo, "vendor/art/runtime/gc/heap-inl.h")
    workaround_pattern = (
        r"windows_x64_low_4gb|MarkCard OOB|Windows x64 NonMoving WB|"
        r"must match low-4g heap"
    )
    for relative, text in (
        ("vendor/art/runtime/runtime.cc", runtime),
        ("vendor/art/runtime/gc/accounting/card_table.cc", card_table_cc),
        ("vendor/art/runtime/gc/accounting/card_table.h", card_table_h),
        ("vendor/art/runtime/gc/heap-inl.h", heap_inl),
    ):
        reject_pattern(text, workaround_pattern, f"forced-low workaround in {relative}")

    for pattern, label in (
        (r"MemMapArenaPool\(/\* low_4gb= \*/ false\)", "runtime arena anywhere policy"),
        (
            r'MemMapArenaPool\(/\* low_4gb= \*/ false, "CompilerMetadata"\)',
            "compiler metadata anywhere policy",
        ),
        (
            r"const bool low_4gb = IsAotCompiler\(\) && "
            r"Is64BitInstructionSet\(kRuntimeISA\)",
            "AOT-only LinearAlloc low policy",
        ),
    ):
        require_pattern(runtime, pattern, label)

    require_pattern(
        card_table_cc,
        r'MapAnonymous\("card table",\s+capacity \+ 256,\s+'
        r"PROT_READ \| PROT_WRITE,\s+/\*low_4gb=\*/ false,",
        "card-table anywhere mapping",
    )
    windows_conditional = r"#ifn?def _WIN32|defined\(_WIN32\)"
    reject_pattern(card_table_cc, windows_conditional, "Windows card-table branch")
    reject_pattern(card_table_h, windows_conditional, "Windows card-table header branch")
    reject_pattern(
        heap_inl,
        rf"AddrIsInCardTable|{windows_conditional}",
        "Windows non-moving write-barrier branch",
    )

    low_pattern = re.compile(r"/\*\s*low_4gb\s*=\s*\*/\s*true")
    observed: set[str] = set()
    runtime_root = art / "runtime"
    for path in runtime_root.rglob("*.cc"):
        relative = path.relative_to(art).as_posix()
        if "test" in relative:
            continue
        if low_pattern.search(path.read_text(encoding="utf-8")):
            observed.add(relative)
    if observed != EXPECTED_LOW_ADDRESS_FILES:
        missing = sorted(EXPECTED_LOW_ADDRESS_FILES - observed)
        unexpected = sorted(observed - EXPECTED_LOW_ADDRESS_FILES)
        fail(f"low-address caller inventory changed: missing={missing} unexpected={unexpected}")

    return {
        "low_address_files": len(observed),
        "page_transition_files": len(transition_files),
        "mspace_lock_assertions": 2,
    }


def main() -> int:
    repo = Path(__file__).resolve().parents[3]
    counts = check_repository(repo)
    print(
        "W013_SOURCE_POLICY_PASS "
        f"low_address_files={counts['low_address_files']} "
        f"page_transition_files={counts['page_transition_files']} "
        f"mspace_lock_assertions={counts['mspace_lock_assertions']} "
        "metadata=anywhere card_mark=unconditional nonmoving_barrier=unconditional"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        print(f"W013_SOURCE_POLICY_FAIL: {error}", file=sys.stderr)
        sys.exit(1)
