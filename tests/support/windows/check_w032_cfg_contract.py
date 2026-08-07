#!/usr/bin/env python3
"""Verify the W-032 Windows boot-OAT CFG source and PE caller contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


class ContractError(RuntimeError):
    """The W-032 source or PE contract is incomplete."""


def _regular_file(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    if not path.is_file() or path.is_symlink():
        raise ContractError(f"required regular file is missing: {path}")
    return path


def _read(repo: Path, relative: str) -> str:
    return _regular_file(repo / relative).read_text(encoding="utf-8")


def _require(text: str, label: str, *markers: str) -> None:
    for marker in markers:
        if marker not in text:
            raise ContractError(f"{label} is missing required text: {marker}")


def _run(tool: Path, *arguments: str) -> str:
    result = subprocess.run(
        [str(_regular_file(tool)), *arguments],
        check=False,
        shell=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ContractError(
            f"{tool.name} failed ({result.returncode}): {result.stdout}{result.stderr}"
        )
    return result.stdout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_source(repo: Path) -> dict[str, int]:
    writer = _read(repo, "vendor/art/dex2oat/linker/oat_writer.cc")
    elf_builder = _read(repo, "vendor/art/libelffile/elf/elf_builder.h")
    runtime = _read(repo, "vendor/art/runtime/multiplatform/windows/aot_cfg_windows.cc")
    oat_file = _read(repo, "vendor/art/runtime/oat/oat_file.cc")
    bridge = _read(repo, "tests/cases/aot-cfg/guarded_invoke_x86_64.S")
    probe = _read(repo, "tests/cases/aot-cfg/probe.cc")

    _require(
        writer,
        "OAT CFG writer",
        "kOatWindowsCfgVersion = 1u",
        "kImageFileMachineAmd64 = 0x8664u",
        "InitWindowsCfgLayout",
        "kOatWindowsCfgChecksumOffset",
        "kOatWindowsCfgBootTrampoline",
    )
    _require(
        elf_builder,
        "ELF CFG transport",
        '".oat_cfg.windows"',
        'return "oatcfgwindows"',
        'return "oatcfgwindowslastword"',
        "kLast = kOatDexLastWord",
    )
    _require(
        runtime,
        "runtime CFG parser",
        "ProcessControlFlowGuardPolicy",
        "kTargetAlignment = 16u",
        "Windows OAT CFG checksum is invalid",
    )
    _require(
        oat_file,
        "OAT runtime integration",
        'FindDynamicSymbolAddress("oatcfgwindows"',
        'FindDynamicSymbolAddress("oatcfgwindowslastword"',
        '".oat_cfg.windows is not contained by one read-only PT_LOAD"',
    )
    _require(
        bridge,
        "guarded quick bridge",
        "@feat.00 = 2048",
        "__guard_dispatch_icall_fptr(%rip)",
        "callq   *%r10",
    )
    _require(
        probe,
        "native CFG observation",
        "GetProcessMitigationPolicy",
        "guarded_quick=pass guarded_jni=pass",
        "target_api_calls=0",
    )
    active = "\n".join((runtime, oat_file, bridge, probe))
    if "SetProcessValidCallTargets" in active:
        raise ContractError("W-032 observation mode calls SetProcessValidCallTargets")
    return {
        "cfg_section_names": 1,
        "dynamic_anchors": 2,
        "guard_dispatch_bridges": 1,
        "target_api_calls": 0,
    }


def check_pe(probe: Path, llvm_readobj: Path) -> dict[str, int]:
    load_config = _run(llvm_readobj, "--coff-load-config", str(probe))
    _require(
        load_config,
        "W-032 probe load configuration",
        "CF_INSTRUMENTED",
        "CF_FUNCTION_TABLE_PRESENT",
        "GuardCFCheckDispatch:",
    )
    dispatch = re.search(r"GuardCFCheckDispatch:\s+0x([0-9A-Fa-f]+)", load_config)
    if dispatch is None or int(dispatch.group(1), 16) == 0:
        raise ContractError("W-032 probe has no CFG dispatch pointer")
    exports = _run(llvm_readobj, "--coff-exports", str(probe))
    _require(exports, "W-032 probe exports", "Java_W032AotCfgProbe_nativeAudit")
    return {"cfg_flags": 2, "guard_dispatch_pointer": 1, "jni_exports": 1}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--llvm-readobj", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    try:
        repo = Path(os.path.abspath(args.repo))
        if not repo.is_dir():
            raise ContractError(f"repository root is missing: {repo}")
        probe = _regular_file(args.probe)
        source = check_source(repo)
        pe = check_pe(probe, args.llvm_readobj)
        record = {
            "schema_version": 1,
            "status": "PASS",
            "source_policy": source,
            "pe_policy": pe,
            "artifact": {"name": probe.name, "sha256": _sha256(probe)},
        }
        result = Path(os.path.abspath(args.result))
        result.parent.mkdir(parents=True, exist_ok=True)
        temporary = result.with_name(result.name + ".tmp")
        temporary.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, result)
        print(
            "W032_CFG_STRUCTURE_PASS cfg_flags=2 guard_dispatch=present "
            "dynamic_anchors=2 target_api_calls=0"
        )
        return 0
    except (ContractError, OSError, UnicodeError, ValueError) as exc:
        print(f"W032_CFG_STRUCTURE_FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
