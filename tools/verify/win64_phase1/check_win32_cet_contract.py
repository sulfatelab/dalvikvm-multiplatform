#!/usr/bin/env python3
"""Verify the Win64 ART CET-shadow-stack-disabled build/runtime contract."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess


CET_MARKER = "IMAGE_DLL_CHARACTERISTICS_EX_CET_COMPAT"
LINK_OPTION = "/CETCOMPAT:NO"


def fail(message: str) -> None:
    raise RuntimeError(message)


def run(*command: str) -> str:
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


def check_source_policy(repo: Path) -> tuple[int, int, int]:
    overlay = (repo / "overlay/port_policy_windows.py").read_text(encoding="utf-8")
    if 'add_ldflags=["LINKER:/CETCOMPAT:NO"]' not in overlay:
        fail("Win64 generator overlay does not explicitly add /CETCOMPAT:NO")

    runtime = (repo / "vendor/art/runtime/runtime.cc").read_text(encoding="utf-8")
    check_index = runtime.find("if (!CheckPlatformProcessPolicy())")
    mem_map_index = runtime.find("MemMap::Init();")
    thread_index = runtime.find("Thread::Startup();")
    if min(check_index, mem_map_index, thread_index) < 0:
        fail("could not find the Win64 process-policy/runtime initialization sequence")
    if not check_index < mem_map_index < thread_index:
        fail("Win64 process-policy guard no longer precedes memory and thread startup")

    cmake_files = []
    for path in (repo / "tools").rglob("CMakeLists.txt"):
        relative = path.relative_to(repo)
        if not any("win64" in part.lower() for part in relative.parts):
            continue
        text = path.read_text(encoding="utf-8")
        cmake_files.append(path)
        if "LINKER:/CETCOMPAT:NO" not in text:
            fail(f"Win64 CMake link policy is missing from {relative}")

    raw_links = []
    for path in (repo / "tools").rglob("*.sh"):
        text = path.read_text(encoding="utf-8")
        if "--target=x86_64-pc-windows-msvc" not in text:
            continue
        if "-fuse-ld" not in text or not re.search(r"(?:^|\s)-o(?:\s|$)", text):
            continue
        raw_links.append(path)
        if LINK_OPTION not in text.upper():
            fail(f"raw Win64 PE link does not pass {LINK_OPTION}: {path.relative_to(repo)}")

    if not cmake_files:
        fail("no Win64 CMake PE producers were audited")
    if not raw_links:
        fail("no raw Win64 PE links were audited")

    packagers = sorted(
        (repo / "tools/win64/host_package").glob("package_win64_*.sh")
    )
    for path in packagers:
        text = path.read_text(encoding="utf-8")
        if "check_win32_cet_contract.py" not in text or "--pe-root" not in text:
            fail(f"Win64 host packager does not enforce the PE audit: {path.relative_to(repo)}")
    if not packagers:
        fail("no Win64 host packagers were audited")
    return len(cmake_files), len(raw_links), len(packagers)


def pe_targets(ninja: str, build: Path) -> list[Path]:
    output = run(ninja, "-C", str(build), "-t", "targets", "all")
    targets = []
    for line in output.splitlines():
        name, separator, _rule = line.partition(": ")
        if not separator or not name.lower().endswith((".dll", ".exe")):
            continue
        targets.append(Path(name))
    if not targets:
        fail(f"no PE link targets found in {build}")
    return sorted(set(targets), key=lambda path: str(path).lower())


def check_link_commands(ninja: str, build: Path, targets: list[Path]) -> None:
    missing = []
    for target in targets:
        commands = run(ninja, "-C", str(build), "-t", "commands", str(target))
        if LINK_OPTION not in commands.upper():
            missing.append(str(target))
    if missing:
        fail("PE link commands missing explicit /CETCOMPAT:NO: " + ", ".join(missing))


def scan_pe(readobj: str, path: Path) -> None:
    output = run(readobj, "--coff-debug-directory", str(path))
    if CET_MARKER in output:
        fail(f"CET-compatible extended DLL characteristic is present: {path}")


def collect_pe_files(roots: list[Path], explicit: list[Path]) -> list[Path]:
    files = set()
    for root in roots:
        if not root.exists():
            fail(f"PE scan root does not exist: {root}")
        for pattern in ("*.dll", "*.exe"):
            files.update(path.resolve() for path in root.rglob(pattern) if path.is_file())
    for path in explicit:
        if not path.is_file():
            fail(f"explicit PE file does not exist: {path}")
        files.add(path.resolve())
    return sorted(files, key=lambda path: str(path).lower())


def main() -> int:
    repo = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build",
        type=Path,
        default=repo / "build/win64_phase1",
        help="configured primary Win64 Ninja build",
    )
    parser.add_argument(
        "--pe-root",
        action="append",
        type=Path,
        default=[],
        help="additional package/build root to scan recursively (repeatable)",
    )
    parser.add_argument(
        "--external-pe",
        action="append",
        type=Path,
        default=[],
        help="external packaged PE such as LLVM libc++ (repeatable)",
    )
    parser.add_argument(
        "--require-built",
        action="store_true",
        help="require every PE target in the primary Ninja graph to exist",
    )
    args = parser.parse_args()

    build = args.build.resolve()
    ninja = require_tool(os.environ.get("NINJA", "ninja"))
    readobj = require_tool(os.environ.get("LLVM_READOBJ", "llvm-readobj"))

    cmake_count, raw_count, packager_count = check_source_policy(repo)
    targets = pe_targets(ninja, build)
    check_link_commands(ninja, build, targets)

    target_files = []
    for target in targets:
        path = build / target
        if path.is_file():
            target_files.append(path)
        elif args.require_built:
            fail(f"required PE target has not been built: {path}")

    external = [path.resolve() for path in args.external_pe]
    if not external:
        win64_env = os.environ.get("WIN64_DEV_ENV")
        if win64_env:
            libcxx = Path(win64_env) / "lib/libcxx/lib/c++.dll"
            if libcxx.is_file():
                external.append(libcxx.resolve())
    files = collect_pe_files(
        [path.resolve() for path in args.pe_root],
        [*target_files, *external],
    )
    if not files:
        fail("no built or external PE files were selected for marker inspection")
    for path in files:
        scan_pe(readobj, path)

    print(
        "WIN32_CET_CONTRACT PASS "
        f"cmake_harnesses={cmake_count} raw_links={raw_count} "
        f"packagers={packager_count} "
        f"link_targets={len(targets)} pe_files={len(files)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
