#!/usr/bin/env python3
"""Fail-closed source audit for the retired W-024 interpreter/JIT workaround."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_regular_text(path: Path, repo_root: Path, errors: list[str]) -> str:
    relative = path.relative_to(repo_root).as_posix()
    if path.is_symlink() or not path.is_file():
        errors.append(f"required regular source is missing: {relative}")
        return ""
    return path.read_text(encoding="utf-8")


def audit_w024_cleanup(repo_root: Path = REPO_ROOT) -> list[str]:
    repo_root = repo_root.resolve()
    errors: list[str] = []
    art = repo_root / "vendor" / "art"
    interpreter_path = art / "runtime" / "interpreter" / "interpreter.cc"
    jit_path = art / "runtime" / "jit" / "jit.cc"
    product_graph = repo_root / "native" / "CMakeLists.txt"
    math_java_path = (
        repo_root / "vendor/libcore/ojluni/src/main/java/java/lang/Math.java"
    )
    math_native_path = repo_root / "vendor/libcore/ojluni/src/main/native/Math.c"

    interpreter = _read_regular_text(interpreter_path, repo_root, errors)
    for retired in (
        "ResolveJniEntryPoint",
        "InterpreterJniGeneric",
        "ART_WINDOWS_X64_INTERPRETER_JNI_TRIPWIRE",
    ):
        if retired in interpreter:
            errors.append(f"legacy interpreter fallback remains: {retired}")
    invariant = "CHECK(!Runtime::Current()->IsStarted());"
    if invariant not in interpreter:
        errors.append("upstream pre-start-only interpreter invariant is missing")

    native_jit_sources = (
        jit_path,
        product_graph,
        repo_root / "tests" / "cases" / "jit-runtime-controls" / "run.py",
        repo_root
        / "tests"
        / "cases"
        / "jvmti-force"
        / "run.py",
        repo_root / "tests" / "cases" / "math-critical" / "run.py",
        repo_root
        / "tests"
        / "support"
        / "windows"
        / "w003_managed_gate.py",
    )
    for path in native_jit_sources:
        if "ART_WINDOWS_X64_JIT_NATIVE" in _read_regular_text(path, repo_root, errors):
            errors.append(
                "legacy native-JIT gate remains: " + path.relative_to(repo_root).as_posix()
            )

    math_java = _read_regular_text(math_java_path, repo_root, errors)
    for declaration in (
        "public static native double ceil(double a);",
        "public static native double floor(double a);",
    ):
        if declaration not in math_java:
            errors.append(f"restored Math native declaration is missing: {declaration}")
    math_native = _read_regular_text(math_native_path, repo_root, errors)
    for registration in (
        'FAST_NATIVE_METHOD(Math, ceil, "(D)D")',
        'FAST_NATIVE_METHOD(Math, floor, "(D)D")',
    ):
        if registration not in math_native:
            errors.append(f"shared Math native registration is missing: {registration}")
    for retired in ("gMethodsWin", "defined(_WIN32)"):
        if retired in math_native:
            errors.append(f"Windows-only Math registration remains: {retired}")

    product_text = _read_regular_text(product_graph, repo_root, errors)
    if "MDVM_WINDOWS_X64_INTERPRETER_JNI_TRIPWIRE" in product_text:
        errors.append("retired interpreter tripwire build option remains")

    retired_package = (
        repo_root
        / "tools"
        / "windows_x64"
        / "host_package"
        / "package_windows_x64_w024_tripwire.sh"
    )
    if retired_package.exists() or retired_package.is_symlink():
        errors.append("retired W-024 tripwire package generator remains")
    return errors


def main() -> int:
    errors = audit_w024_cleanup()
    if errors:
        for error in errors:
            print(error)
        return 1
    print("W-024 cleanup source check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
