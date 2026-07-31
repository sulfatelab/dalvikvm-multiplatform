#!/usr/bin/env python3
"""Check the W-025 JIT-3 lifecycle probe and Windows nterp FP-return fix."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(text: str, label: str, *markers: str) -> None:
    for marker in markers:
        if marker not in text:
            fail(f"{label} is missing {marker!r}")


def command(*args: str) -> str:
    result = subprocess.run(args, text=True, capture_output=True)
    if result.returncode != 0:
        fail(f"command failed ({result.returncode}): {' '.join(args)}\n"
             f"{result.stdout}{result.stderr}")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    build = args.build.resolve()

    native_source = repo / "tests/cases/jit-lifecycle-stress/probe.cc"
    java_source = repo / "tests/cases/jit-lifecycle-stress/W025JitLifecycleStressProbe.java"
    nterp_source = repo / "vendor/art/runtime/interpreter/mterp/x86_64ng/main.S"
    probe_dll = build / "libw025jitlifecyclestressprobe.dll"
    probe_jar = build / "run/w025jitlifecyclestressprobe.jar"
    art_dll = build / "art.dll"
    for path in (native_source, java_source, nterp_source, probe_dll, probe_jar, art_dll):
        if not path.is_file():
            fail(f"required input is missing: {path}")

    native = native_source.read_text(encoding="utf-8")
    require(
        native,
        "native lifecycle probe",
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

    java = java_source.read_text(encoding="utf-8")
    managed_count = len(re.findall(r"private static int target\d{2}\(", java))
    native_count = len(re.findall(r"private static native (?!boolean nativeRun)", java))
    if managed_count != 16 or native_count != 8:
        fail(f"unexpected method matrix managed={managed_count} native={native_count}")
    require(
        java,
        "Java lifecycle probe",
        "Double.doubleToLongBits(d) != Double.doubleToLongBits(6.25)",
        "Float.floatToIntBits(f) != Float.floatToIntBits(6.5f)",
        '" jni_values=pass"',
    )

    nterp = nterp_source.read_text(encoding="utf-8")
    normal_return = re.search(
        r"\.Lreturn_float_.*?\.Ldone_return_", nterp, flags=re.DOTALL)
    range_return = re.search(
        r"\.Lreturn_range_double_.*?\.endm", nterp, flags=re.DOTALL)
    if normal_return is None or range_return is None:
        fail("could not isolate nterp FP return blocks")
    return_text = normal_return.group(0) + range_return.group(0)
    require(
        return_text,
        "nterp FP return blocks",
        "movd %xmm0, %eax",
        "movq %xmm0, %rax",
    )
    if "movd %eax, %xmm0" in return_text or "movq %rax, %xmm0" in return_text:
        fail("nterp FP return block still prefers RAX over XMM0")

    exports = command("llvm-readobj", "--coff-exports", str(probe_dll))
    required_exports = (
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
    for symbol in required_exports:
        if f"Name: {symbol}" not in exports:
            fail(f"probe DLL is missing export {symbol}")

    print("status=PASS")
    print(f"managed_methods={managed_count}")
    print(f"jni_methods={native_count}")
    print("synthetic_rbp=1")
    print("active_unwind_quiescence=1")
    print("lifecycle_invalidate_collect_reuse=1")
    print("nterp_fp_result_source=xmm0")
    print("callback_tables=0")
    print(f"probe_exports={len(required_exports)}")
    print(f"probe_dll_sha256={sha256(probe_dll)}")
    print(f"probe_jar_sha256={sha256(probe_jar)}")
    print(f"art_sha256={sha256(art_dll)}")
    print("W025_JIT3_SOURCE_CHECK_PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"W025_JIT3_SOURCE_CHECK_FAIL: {error}", file=sys.stderr)
        sys.exit(1)
