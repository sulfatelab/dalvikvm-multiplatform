#!/usr/bin/env python3
"""Verify the Win32 ART CET-shadow-stack-disabled build/runtime contract."""

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


def check_source_policy(repo: Path) -> dict[str, int]:
    overlay = (repo / "overlay/port_policy_windows.py").read_text(encoding="utf-8")
    if 'add_ldflags=["LINKER:/CETCOMPAT:NO"]' not in overlay:
        fail("Windows x64 generator overlay does not explicitly add /CETCOMPAT:NO")

    runtime = (repo / "vendor/art/runtime/runtime.cc").read_text(encoding="utf-8")
    check_index = runtime.find("if (!CheckPlatformProcessPolicy())")
    mem_map_index = runtime.find("MemMap::Init();")
    thread_index = runtime.find("Thread::Startup();")
    if min(check_index, mem_map_index, thread_index) < 0:
        fail("could not find the Windows x64 process-policy/runtime initialization sequence")
    if not check_index < mem_map_index < thread_index:
        fail("Windows x64 process-policy guard no longer precedes memory and thread startup")

    test_graph = (repo / "tests" / "CMakeLists.txt").read_text(encoding="utf-8")
    if 'set(_art_no_cet "LINKER:/CETCOMPAT:NO")' not in test_graph:
        fail("Windows test graph does not define the shared /CETCOMPAT:NO policy")
    if not re.search(
        r"target_link_options\(art-test-target-policy INTERFACE\s+"
        r'-fuse-ld=lld "\$\{_art_no_cet\}"\)',
        test_graph,
    ):
        fail("Windows test target policy does not propagate /CETCOMPAT:NO")

    product_graph = (repo / "native" / "CMakeLists.txt").read_text(encoding="utf-8")
    if 'target_link_options(sigchain PRIVATE "LINKER:/CETCOMPAT:NO")' not in product_graph:
        fail("handwritten Windows sigchain target does not disable CET compatibility")

    raw_links = []
    for path in (repo / "tools").rglob("*.sh"):
        text = path.read_text(encoding="utf-8")
        if "--target=x86_64-pc-windows-msvc" not in text:
            continue
        if "-fuse-ld" not in text or not re.search(r"(?:^|\s)-o(?:\s|$)", text):
            continue
        raw_links.append(path)
        if LINK_OPTION not in text.upper():
            fail(f"raw Windows x64 PE link does not pass {LINK_OPTION}: {path.relative_to(repo)}")

    if raw_links:
        fail(
            "raw Windows x64 PE link scripts bypass the unified graph: "
            + ", ".join(str(path.relative_to(repo)) for path in raw_links)
        )

    packagers = sorted(
        (repo / "tools/windows_x64/host_package").glob("package_windows_x64_*.sh")
    )
    if packagers:
        fail(
            "legacy Windows x64 shell packagers remain: "
            + ", ".join(str(path.relative_to(repo)) for path in packagers)
        )
    return {"raw_links": len(raw_links), "legacy_packagers": len(packagers)}


def pe_targets(ninja: str, build: Path) -> list[Path]:
    output = run(ninja, "-C", str(build), "-t", "targets", "all")
    targets = []
    for line in output.splitlines():
        name, separator, rule = line.partition(": ")
        if (
            not separator
            or rule == "phony"
            or not name.lower().endswith((".dll", ".exe"))
        ):
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
        default=repo / "out/windows-x86_64-msvc/RelWithDebInfo",
        help="configured primary Windows x64 Ninja build",
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

    source_policy = check_source_policy(repo)
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
        windows_x64_env = os.environ.get("WINDOWS_X64_DEV_ENV")
        if windows_x64_env:
            libcxx = Path(windows_x64_env) / "lib/libcxx/lib/c++.dll"
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
        f"generated_policy=1 raw_links={source_policy['raw_links']} "
        f"legacy_packagers={source_policy['legacy_packagers']} "
        f"link_targets={len(targets)} pe_files={len(files)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
