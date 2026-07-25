#!/usr/bin/env python3
"""Verify the Win64 W-004 direct Runtime::instance_ load contract."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


RUNTIME_INSTANCE = "?instance_@Runtime@art@@0PEAV12@EA"
RETIRED_HELPER = "art_Runtime_instance_ptr"


def fail(message: str) -> None:
    raise RuntimeError(message)


def run(tool: str, *args: str) -> str:
    command = [tool, *args]
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode != 0:
        fail(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
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


def count_named_entry(output: str, symbol: str) -> int:
    return sum(line.strip() == f"Name: {symbol}" for line in output.splitlines())


def check_source(repo: Path) -> None:
    art = repo / "vendor/art"
    asm_support = art / "runtime/arch/x86_64/asm_support_x86_64.S"
    text = asm_support.read_text(encoding="utf-8")
    direct_load = f'movq "{RUNTIME_INSTANCE}"(%rip), REG_VAR(reg)'
    if direct_load not in text:
        fail("Win64 LOAD_RUNTIME_INSTANCE is not the expected direct RIP-relative load")
    linux_load = (
        "movq _ZN3art7Runtime9instance_E@GOTPCREL(%rip), REG_VAR(reg)\n"
        "    movq (REG_VAR(reg)), REG_VAR(reg)"
    )
    if linux_load not in text:
        fail("the upstream Linux x86_64 Runtime::instance_ load changed")

    for path in (art / "runtime").rglob("*"):
        if path.suffix not in {".cc", ".h", ".S"}:
            continue
        source = path.read_text(encoding="utf-8", errors="replace")
        if RETIRED_HELPER in source:
            fail(f"retired helper remains in ART source: {path.relative_to(repo)}")
        if "InstanceLocation()" in source:
            fail(f"helper-only InstanceLocation remains: {path.relative_to(repo)}")

    quick = (
        art / "runtime/arch/x86_64/quick_entrypoints_x86_64.S"
    ).read_text(encoding="utf-8")
    quick_sequence = (
        "    LOAD_RUNTIME_INSTANCE rcx\n"
        "    movq RUNTIME_INSTRUMENTATION_OFFSET(%rcx), %rcx"
    )
    if quick_sequence not in quick:
        fail("generic JNI still has work between the direct load and instrumentation access")

    jni = (
        art / "runtime/arch/x86_64/jni_entrypoints_x86_64.S"
    ).read_text(encoding="utf-8")
    jni_sequence = (
        "    LOAD_RUNTIME_INSTANCE r10\n"
        "    movq RUNTIME_SAVE_REFS_AND_ARGS_METHOD_OFFSET(%r10), %r10"
    )
    if jni_sequence not in jni:
        fail("critical JNI still has helper-specific work after LOAD_RUNTIME_INSTANCE")


def check_object(
    readobj: str,
    objdump: str,
    label: str,
    path: Path,
) -> int:
    relocations = run(readobj, "--relocations", str(path))
    direct_count = relocations.count(RUNTIME_INSTANCE)
    helper_count = relocations.count(RETIRED_HELPER)
    if direct_count == 0:
        fail(f"{label} has no direct Runtime::instance_ relocation: {path}")
    if helper_count != 0:
        fail(f"{label} still has {helper_count} retired helper relocations: {path}")

    disassembly = run(objdump, "-dr", str(path)).splitlines()
    direct_lines = [i for i, line in enumerate(disassembly) if RUNTIME_INSTANCE in line]
    if len(direct_lines) != direct_count:
        fail(
            f"{label} relocation/disassembly count mismatch: "
            f"readobj={direct_count} objdump={len(direct_lines)}"
        )
    for index in direct_lines:
        if index == 0:
            fail(f"{label} direct relocation has no instruction")
        instruction = disassembly[index - 1]
        if "movq" not in instruction or "(%rip)" not in instruction:
            fail(f"{label} direct relocation is not attached to RIP-relative movq: {instruction}")
    return direct_count


def check_build_dependencies(ninja: str, build: Path, objects: list[Path], repo: Path) -> None:
    support = str(repo / "vendor/art/runtime/arch/x86_64/asm_support_x86_64.S")
    for path in objects:
        target = str(path.relative_to(build))
        query = run(ninja, "-C", str(build), "-t", "query", target)
        if support not in query:
            fail(f"incremental build dependency is missing for {target}")


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

    readobj = require_tool(os.environ.get("LLVM_READOBJ", "llvm-readobj"))
    objdump = require_tool(os.environ.get("LLVM_OBJDUMP", "llvm-objdump"))
    ninja = require_tool(os.environ.get("NINJA", "ninja"))

    art_dll = build / "art.dll"
    jvmti_dll = build / "openjdkjvmti.dll"
    for path in (art_dll, jvmti_dll):
        if not path.is_file():
            fail(f"required Win64 artifact is missing: {path}")

    object_root = build / "CMakeFiles/art.dir"
    objects = {
        "quick": find_one(object_root, "quick_entrypoints_x86_64.S.obj"),
        "jni": find_one(object_root, "jni_entrypoints_x86_64.S.obj"),
        "nterp": find_one(object_root, "mterp_x86_64.S.obj"),
    }
    dependency_objects = [
        find_one(object_root, "memcmp16_x86_64.S.obj"),
        find_one(object_root, "native_entrypoints_x86_64.S.obj"),
        *objects.values(),
    ]

    check_source(repo)
    counts = {
        label: check_object(readobj, objdump, label, path)
        for label, path in objects.items()
    }
    check_build_dependencies(ninja, build, dependency_objects, repo)

    exports = run(readobj, "--coff-exports", str(art_dll))
    if count_named_entry(exports, RUNTIME_INSTANCE) != 1:
        fail("art.dll does not export exactly one Runtime::instance_ data symbol")
    if RETIRED_HELPER in exports:
        fail("art.dll still exports the retired runtime-instance helper")

    imports = run(readobj, "--coff-imports", str(jvmti_dll))
    if imports.count(f"Symbol: {RUNTIME_INSTANCE}") != 1:
        fail("openjdkjvmti.dll does not import Runtime::instance_ exactly once")
    if RETIRED_HELPER in imports:
        fail("openjdkjvmti.dll unexpectedly imports the retired helper")

    total = sum(counts.values())
    print(
        "W-004 runtime load structural check: PASS "
        f"(quick={counts['quick']} jni={counts['jni']} "
        f"nterp={counts['nterp']} total={total})"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as error:
        print(f"W-004 runtime load structural check: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
