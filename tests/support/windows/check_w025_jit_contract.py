#!/usr/bin/env python3
"""Verify the unified W-025 Windows JIT source and PE contract."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


_SUPPORT_ROOT = Path(__file__).parents[1]
if str(_SUPPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SUPPORT_ROOT))

import runtime_gate  # noqa: E402


_RETIRED_KEY = "ART_WINDOWS_X64_JIT_DUAL"
_RETIRED_FALLBACK = "falling back to single-view (J-1)"
_JNI_EXPORTS = (
    "Java_W025JitLifecycleStressProbe_nativeRun",
    "Java_W025JitLifecycleStressProbe_nativeI",
    "Java_W025JitLifecycleStressProbe_nativeJ",
    "Java_W025JitLifecycleStressProbe_nativeD",
    "Java_W025JitLifecycleStressProbe_nativeF",
    "Java_W025JitLifecycleStressProbe_nativeZ",
    "Java_W025JitLifecycleStressProbe_nativeL",
    "Java_W025JitLifecycleStressProbe_nativeMix",
    "Java_W025JitLifecycleStressProbe_nativeV",
)


def _fail(message: str) -> None:
    raise RuntimeError(message)


def _read(repo: Path, relative: str) -> str:
    path = repo / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        _fail(f"cannot read {relative}: {exc}")


def _require(text: str, label: str, *markers: str) -> None:
    for marker in markers:
        if marker not in text:
            _fail(f"{label} is missing required contract text: {marker}")


def _forbid(text: str, label: str, *markers: str) -> None:
    for marker in markers:
        if marker in text:
            _fail(f"{label} contains retired contract text: {marker}")


def _run(tool: Path, *arguments: str) -> str:
    tool = runtime_gate._regular_file(str(tool))
    result = subprocess.run(
        [str(tool), *arguments],
        text=True,
        capture_output=True,
        check=False,
        shell=False,
    )
    if result.returncode != 0:
        _fail(
            f"{tool.name} failed ({result.returncode}) for {arguments[0]}: "
            f"{result.stdout}{result.stderr}"
        )
    return result.stdout


def check_source_policy(repo: Path) -> dict[str, int]:
    mem_map = _read(repo, "vendor/art/libartbase/base/mem_map_windows.cc")
    jit_region = _read(repo, "vendor/art/runtime/jit/jit_memory_region.cc")
    section_probe = _read(repo, "tests/cases/jit-section-policy/probe.cc")
    stress_native = _read(repo, "tests/cases/jit-lifecycle-stress/probe.cc")
    stress_java = _read(
        repo,
        "tests/cases/jit-lifecycle-stress/W025JitLifecycleStressProbe.java",
    )
    nterp = _read(
        repo,
        "vendor/art/runtime/interpreter/mterp/x86_64ng/main.S",
    )
    codegen = _read(repo, "tools/bp2cmake/bp2cmake/codegen.py")
    native_cmake = _read(repo, "native/CMakeLists.txt")
    controls = _read(repo, "tests/cases/jit-runtime-controls/run.py")

    create_match = re.search(
        r"void\* MemMap::CreatePageFileSection\(.*?\n\}",
        mem_map,
        re.DOTALL,
    )
    if create_match is None:
        _fail("CreatePageFileSection definition is missing")
    create = create_match.group(0)
    _require(
        create,
        "CreatePageFileSection",
        "CreateFileMappingW(",
        "INVALID_HANDLE_VALUE",
        "PAGE_EXECUTE_READWRITE",
        "nullptr);",
    )
    _forbid(
        create,
        "CreatePageFileSection",
        "CreateFileW(",
        "CreateFileA(",
        "GetTempPath",
        "mkstemp",
    )

    _require(
        jit_region,
        "JitMemoryRegion Windows section policy",
        "This is the only Windows JIT memory path.",
        "MemMap::CreatePageFileSection(capacity",
        "kProtRX,",
        "/*low_4gb=*/true",
        "kProtRW,",
        "CHECK_EQ(primary.End(), exec.Begin())",
        "CheckJitSectionView(primary, primary.Begin(), PAGE_READONLY)",
        "CheckJitSectionView(exec, primary.Begin(), PAGE_EXECUTE_READ)",
        "CheckJitSectionView(writable, writable.Begin(), PAGE_READWRITE)",
        "CheckJitSectionView(non_exec, writable.Begin(), PAGE_READWRITE)",
        'dual_view_error = "Windows x64 JIT dual-view CreateFileMapping failed: " + j2_error;',
        'dual_view_error = "Windows x64 JIT dual-view construction failed: " + j2_error;',
        "*error_msg = dual_view_error;",
        "CHECK(j2_complete);",
        "#else\n    // Single view of JIT code cache case.",
    )
    _forbid(jit_region, "JitMemoryRegion", _RETIRED_KEY, _RETIRED_FALLBACK)

    _require(
        section_probe,
        "W025SectionPolicyProbe",
        "free_end - reserve_begin",
        "ReserveExact(reserve_begin, reserve_size, reservations)",
        "PAGE_EXECUTE_READWRITE | SEC_COMMIT",
    )
    _forbid(section_probe, "W025SectionPolicyProbe", "kReserveChunk")

    _require(
        stress_native,
        "native lifecycle stress probe",
        "::RtlLookupFunctionEntry(",
        "::RtlVirtualUnwind(",
        "context.Rbp = synthetic_rsp;",
        "active_unwinds",
        "WaitForUnwindReaders(&sampler)",
        "code_cache->InvalidateAllCompiledCode();",
        "code_cache->DoCollection(self);",
        "exact_reuse == expected_reuse",
        "missing_live == 0u",
        "stale_dead == 0u",
        "unwind_failures == 0u",
        '<< " callback_tables=0\\n"',
    )
    managed_count = len(re.findall(r"private static int target\d{2}\(", stress_java))
    native_count = len(
        re.findall(r"private static native (?!boolean nativeRun)", stress_java)
    )
    if managed_count != 16 or native_count != 8:
        _fail(
            f"unexpected lifecycle method matrix: managed={managed_count}, "
            f"jni={native_count}"
        )
    _require(
        stress_java,
        "managed lifecycle stress probe",
        "Double.doubleToLongBits(d) != Double.doubleToLongBits(6.25)",
        "Float.floatToIntBits(f) != Float.floatToIntBits(6.5f)",
        '" jni_values=pass"',
    )

    normal_return = re.search(
        r"\.Lreturn_float_.*?\.Ldone_return_",
        nterp,
        flags=re.DOTALL,
    )
    range_return = re.search(
        r"\.Lreturn_range_double_.*?\.endm",
        nterp,
        flags=re.DOTALL,
    )
    if normal_return is None or range_return is None:
        _fail("could not isolate the nterp floating-point return blocks")
    return_text = normal_return.group(0) + range_return.group(0)
    _require(
        return_text,
        "nterp floating-point return blocks",
        "movd %xmm0, %eax",
        "movq %xmm0, %rax",
    )
    _forbid(
        return_text,
        "nterp floating-point return blocks",
        "movd %eax, %xmm0",
        "movq %rax, %xmm0",
    )
    _require(
        nterp,
        "nterp ABI policy",
        "ART quick/JNI hard-float returns live in xmm0 on Windows and Linux.",
    )
    _require(
        codegen,
        "bounded JIT inspection export overlay",
        '"art/runtime/jit/jit_code_cache.h"',
        "EXPORT LIBART_PE_API bool GetGarbageCollectCode()",
        "EXPORT LIBART_PE_API JitMemoryRegion* GetCurrentRegion();",
    )
    _require(
        native_cmake,
        "JIT inspection defining-translation-unit overlay",
        '"${MDVM_ART_ROOT_DIR}/art/runtime/jit/jit_code_cache.cc"',
        "art/windows-pe-headers/art/runtime/jit/jit_code_cache.h",
    )
    _require(
        controls,
        "unified JIT runtime controls",
        'name="default-verbose"',
        'name="environment-disabled"',
        'name="xusejit-disabled"',
        'name="filter"',
        'name="exclude"',
        'name="quiet"',
        'name="retired-optout"',
        '"ART_WINDOWS_X64_JIT_DUAL": "0"',
        '"ART_WINDOWS_X64_JIT_FILTER": "Hello"',
        '"Windows x64 JIT dual-view (J-2) created"',
        'required_compile_substrings=("Hello",)',
    )
    return {
        "pagefile_section_implementations": 1,
        "managed_methods": managed_count,
        "jni_methods": native_count,
        "nterp_xmm0_return_forms": 2,
        "windows_jit_memory_paths": 1,
        "pe_jit_inspection_exports": 2,
        "jit_control_cases": 7,
    }


def check_pe_policy(
    *,
    readobj: Path,
    art: Path,
    section_probe: Path,
    stress_probe: Path,
) -> dict[str, int]:
    art = runtime_gate._regular_file(str(art))
    section_probe = runtime_gate._regular_file(str(section_probe))
    stress_probe = runtime_gate._regular_file(str(stress_probe))
    load_config = _run(readobj, "--coff-load-config", str(section_probe))
    _require(
        load_config,
        "W025SectionPolicyProbe load configuration",
        "CF_INSTRUMENTED",
        "CF_FUNCTION_TABLE_PRESENT",
    )
    imports = _run(readobj, "--coff-imports", str(section_probe))
    required_imports = (
        "CreateFileMappingW",
        "MapViewOfFile3",
        "K32GetMappedFileNameW",
    )
    for symbol in required_imports:
        if f"Symbol: {symbol}" not in imports:
            _fail(f"section-policy probe does not import {symbol}")

    exports = _run(readobj, "--coff-exports", str(stress_probe))
    for symbol in _JNI_EXPORTS:
        if f"Name: {symbol}" not in exports:
            _fail(f"lifecycle stress probe does not export {symbol}")
    art_exports = _run(readobj, "--coff-exports", str(art))
    for symbol in ("GetCurrentRegion@JitCodeCache", "GetGarbageCollectCode@JitCodeCache"):
        if symbol not in art_exports:
            _fail(f"art.dll does not export the bounded JIT inspection method {symbol}")
    return {
        "cfg_flags": 2,
        "section_imports": len(required_imports),
        "jni_exports": len(_JNI_EXPORTS),
        "art_jit_exports": 2,
    }


def check_art_binary(art: Path) -> dict[str, int]:
    art = runtime_gate._regular_file(str(art))
    data = art.read_bytes()
    for marker in (_RETIRED_KEY, _RETIRED_FALLBACK):
        if marker.encode("ascii") in data or marker.encode("utf-16-le") in data:
            _fail(f"{art.name} contains retired Windows JIT marker {marker!r}")
    required = (
        "Windows x64 JIT dual-view CreateFileMapping failed:",
        "Windows x64 JIT dual-view construction failed:",
        "Windows x64 JIT dual-view (J-2) created:",
    )
    for marker in required:
        if marker.encode("ascii") not in data:
            _fail(f"{art.name} is missing fail-closed Windows JIT marker {marker!r}")
    return {
        "required_markers": len(required),
        "retired_markers": 0,
    }


def run_review(
    *,
    target_id: str,
    repo: Path,
    art: Path,
    section_probe: Path,
    stress_probe: Path,
    llvm_readobj: Path,
    result: Path,
) -> dict[str, object]:
    repo = Path(os.path.abspath(repo))
    if not repo.is_dir():
        _fail("repository root is missing")
    source_counts = check_source_policy(repo)
    pe_counts = check_pe_policy(
        readobj=llvm_readobj,
        art=art,
        section_probe=section_probe,
        stress_probe=stress_probe,
    )
    binary_counts = check_art_binary(art)
    artifacts = {
        "art": runtime_gate._regular_file(str(art)),
        "section_probe": runtime_gate._regular_file(str(section_probe)),
        "stress_probe": runtime_gate._regular_file(str(stress_probe)),
    }
    record: dict[str, object] = {
        "schema_version": 1,
        "status": "PASS",
        "target_id": target_id,
        "source_policy": source_counts,
        "pe_policy": pe_counts,
        "binary_policy": binary_counts,
        "artifacts": {
            name: {"name": path.name, "sha256": runtime_gate._sha256(path)}
            for name, path in sorted(artifacts.items())
        },
    }
    result = runtime_gate._managed_path(result, allow_missing=True)
    result.parent.mkdir(parents=True, exist_ok=True)
    runtime_gate._managed_path(result.parent)
    temporary = result.with_name(result.name + ".tmp")
    temporary.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, result)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--art", type=Path, required=True)
    parser.add_argument("--section-probe", type=Path, required=True)
    parser.add_argument("--stress-probe", type=Path, required=True)
    parser.add_argument("--llvm-readobj", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    try:
        record = run_review(
            target_id=args.target_id,
            repo=args.repo,
            art=args.art,
            section_probe=args.section_probe,
            stress_probe=args.stress_probe,
            llvm_readobj=args.llvm_readobj,
            result=args.result,
        )
        print(
            "W025_JIT_CONTRACT_PASS "
            f"target={record['target_id']} "
            f"managed_methods={record['source_policy']['managed_methods']} "
            f"jni_methods={record['source_policy']['jni_methods']} "
            f"jni_exports={record['pe_policy']['jni_exports']} "
            "windows_memory_paths=1 j1_paths=0"
        )
        return 0
    except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
        print(f"W025_JIT_CONTRACT_FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
