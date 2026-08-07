#!/usr/bin/env python3
"""Build and validate the eight W-032 Windows metadata ELF layouts."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys


class LayoutError(RuntimeError):
    """The W-032 layout matrix is incomplete or malformed."""


def _regular_file(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    if not path.is_file() or path.is_symlink():
        raise LayoutError(f"required regular file is missing: {path}")
    return path


def _directory(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    if not path.is_dir() or path.is_symlink():
        raise LayoutError(f"required directory is missing: {path}")
    return path


def _prepare_root(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    if path.is_symlink():
        raise LayoutError(f"refusing symbolic-link work root: {path}")
    if path.exists():
        if not path.is_dir():
            raise LayoutError(f"work root is not a directory: {path}")
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def _symbols(
    data: bytes,
    raw_sections: list[tuple[int, ...]],
    sections: dict[str, tuple[int, tuple[int, ...]]],
) -> dict[str, tuple[int, int, int]]:
    _, dynsym = sections[".dynsym"]
    dynsym_offset, dynsym_size, dynstr_index, entry_size = (
        dynsym[4],
        dynsym[5],
        dynsym[6],
        dynsym[9],
    )
    if dynstr_index >= len(raw_sections) or entry_size != 24:
        raise LayoutError("invalid dynamic-symbol dimensions")
    dynstr = raw_sections[dynstr_index]
    strings = data[dynstr[4] : dynstr[4] + dynstr[5]]
    result: dict[str, tuple[int, int, int]] = {}
    for offset in range(dynsym_offset, dynsym_offset + dynsym_size, entry_size):
        name_offset, _info, _other, section_index, value, size = struct.unpack_from(
            "<IBBHQQ", data, offset
        )
        if name_offset >= len(strings):
            raise LayoutError("dynamic symbol has an invalid name offset")
        end = strings.find(b"\0", name_offset)
        if end < 0:
            raise LayoutError("dynamic symbol has an unterminated name")
        name = strings[name_offset:end].decode("ascii", errors="strict")
        if name:
            if name in result:
                raise LayoutError(f"duplicate dynamic symbol: {name}")
            result[name] = (section_index, value, size)
    return result


def _containing_loads(
    section: tuple[int, ...], load_segments: list[tuple[int, ...]]
) -> list[tuple[int, tuple[int, ...]]]:
    file_offset, size = section[4], section[5]
    address = section[3]
    return [
        (index, segment)
        for index, segment in enumerate(load_segments)
        if segment[2] <= file_offset
        and file_offset + size <= segment[2] + segment[5]
        and segment[3] <= address
        and address + size <= segment[3] + segment[6]
    ]


def _validate_case(
    path: Path,
    *,
    has_relro: bool,
    has_unwind: bool,
    has_cfg: bool,
    reader,
) -> dict[str, object]:
    data, load_segments, raw_sections, sections = reader(path)
    required = {".rodata", ".text", ".bss", ".dynsym", ".dynstr"}
    missing = sorted(required - sections.keys())
    if missing:
        raise LayoutError(f"{path.name} is missing sections: {missing}")

    expected_optional = {
        ".data.img.rel.ro": has_relro,
        ".oat_unwind.windows": has_unwind,
        ".oat_cfg.windows": has_cfg,
    }
    for name, expected in expected_optional.items():
        if (name in sections) != expected:
            raise LayoutError(f"{path.name} has unexpected presence for {name}")

    ordered_names = [".rodata", ".text"]
    if has_relro:
        ordered_names.append(".data.img.rel.ro")
    if has_unwind:
        ordered_names.append(".oat_unwind.windows")
    if has_cfg:
        ordered_names.append(".oat_cfg.windows")
    ordered_names.append(".bss")
    indices = [sections[name][0] for name in ordered_names]
    if indices != sorted(indices) or len(indices) != len(set(indices)):
        raise LayoutError(f"{path.name} section order is invalid: {ordered_names}")

    for segment in load_segments:
        if segment[1] & 0x3 == 0x3:
            raise LayoutError(f"{path.name} contains a W+X PT_LOAD")
        if segment[7] != 0x10000:
            raise LayoutError(f"{path.name} has non-64-KiB PT_LOAD alignment")
        if segment[2] % segment[7] != segment[3] % segment[7]:
            raise LayoutError(f"{path.name} violates PT_LOAD congruence")

    text = sections[".text"][1]
    if text[8] != 0x10000 or text[3] % 0x10000 or text[4] % 0x10000:
        raise LayoutError(f"{path.name} has an invalid .text boundary")
    if has_relro:
        relro = sections[".data.img.rel.ro"][1]
        matches = _containing_loads(relro, load_segments)
        if len(matches) != 1 or matches[0][1][1] != 0x6:
            raise LayoutError(f"{path.name} has an invalid relro PT_LOAD")

    metadata_names = [
        name
        for name in (".oat_unwind.windows", ".oat_cfg.windows")
        if name in sections
    ]
    metadata_segment: int | None = None
    for name in metadata_names:
        section = sections[name][1]
        matches = _containing_loads(section, load_segments)
        if len(matches) != 1 or matches[0][1][1] != 0x4:
            raise LayoutError(f"{path.name} has an invalid {name} PT_LOAD")
        if metadata_segment is None:
            metadata_segment = matches[0][0]
        elif metadata_segment != matches[0][0]:
            raise LayoutError(f"{path.name} splits Windows metadata PT_LOADs")
    if metadata_names:
        first = sections[metadata_names[0]][1]
        if first[3] % 0x10000 or first[4] % 0x10000 or first[8] != 0x10000:
            raise LayoutError(f"{path.name} does not align its first metadata section")
    if has_cfg:
        cfg_alignment = sections[".oat_cfg.windows"][1][8]
        expected_cfg_alignment = 4 if has_unwind else 0x10000
        if cfg_alignment != expected_cfg_alignment:
            raise LayoutError(
                f"{path.name} has CFG alignment {cfg_alignment:#x}, "
                f"expected {expected_cfg_alignment:#x}"
            )

    symbols = _symbols(data, raw_sections, sections)
    expected_windows_symbols = {
        "oatunwindwindows": has_unwind,
        "oatunwindwindowslastword": has_unwind,
        "oatcfgwindows": has_cfg,
        "oatcfgwindowslastword": has_cfg,
    }
    for name, expected in expected_windows_symbols.items():
        if (name in symbols) != expected:
            raise LayoutError(f"{path.name} has unexpected dynamic symbol {name}")
    text_index, text_section = sections[".text"]
    if symbols.get("oatlastword") != (
        text_index,
        text_section[3] + text_section[5] - 4,
        4,
    ):
        raise LayoutError(f"{path.name} changed oatlastword semantics")
    for section_name, begin_name, end_name in (
        (".oat_unwind.windows", "oatunwindwindows", "oatunwindwindowslastword"),
        (".oat_cfg.windows", "oatcfgwindows", "oatcfgwindowslastword"),
    ):
        if section_name not in sections:
            continue
        section_index, section = sections[section_name]
        if symbols.get(begin_name) != (section_index, section[3], section[5]):
            raise LayoutError(f"{path.name} has an invalid {begin_name} anchor")
        if symbols.get(end_name) != (
            section_index,
            section[3] + section[5] - 4,
            4,
        ):
            raise LayoutError(f"{path.name} has an invalid {end_name} anchor")

    return {
        "file": path.name,
        "relro": has_relro,
        "unwind": has_unwind,
        "cfg": has_cfg,
        "metadata_segment": metadata_segment,
        "load_segments": len(load_segments),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--library-dir", type=Path, action="append", default=[])
    args = parser.parse_args()
    try:
        repo = Path(os.path.abspath(args.repo))
        sys.path.insert(0, str(repo / "tools"))
        import run_dex2oat_no_image  # pylint: disable=import-outside-toplevel

        probe = _regular_file(args.probe)
        work_root = _prepare_root(args.work_root)
        environment = dict(os.environ)
        if os.name == "nt":
            library_dirs = [_directory(path) for path in args.library_dir]
            system_root = environment.get("SystemRoot", r"C:\Windows")
            environment["PATH"] = os.pathsep.join(
                [
                    *(str(path) for path in library_dirs),
                    str(Path(system_root) / "System32"),
                ]
            )
        completed = subprocess.run(
            [str(probe), str(work_root)],
            check=False,
            shell=False,
            capture_output=True,
            text=True,
            timeout=60,
            env=environment,
        )
        if completed.returncode != 0:
            raise LayoutError(
                f"layout probe failed ({completed.returncode}): "
                f"{completed.stdout}{completed.stderr}"
            )
        marker = "W032_CFG_LAYOUT_EMIT_PASS cases=8 segment_alignment=65536"
        if marker not in completed.stdout:
            raise LayoutError(f"layout probe omitted marker: {marker}")

        records = []
        for has_relro in (False, True):
            for metadata_name, has_unwind, has_cfg in (
                ("neither", False, False),
                ("unwind", True, False),
                ("cfg", False, True),
                ("both", True, True),
            ):
                suffix = "relro" if has_relro else "no-relro"
                path = _regular_file(work_root / f"{metadata_name}-{suffix}.oat")
                records.append(
                    _validate_case(
                        path,
                        has_relro=has_relro,
                        has_unwind=has_unwind,
                        has_cfg=has_cfg,
                        reader=run_dex2oat_no_image._read_windows_boot_oat_layout,
                    )
                )
        if len(records) != 8:
            raise LayoutError("layout matrix did not produce exactly eight cases")

        record = {
            "schema_version": 1,
            "status": "PASS",
            "cases": records,
            "case_count": len(records),
            "metadata_segment_cases": sum(
                item["metadata_segment"] is not None for item in records
            ),
            "shared_metadata_segment_cases": sum(
                item["unwind"] and item["cfg"] for item in records
            ),
        }
        result = Path(os.path.abspath(args.result))
        result.parent.mkdir(parents=True, exist_ok=True)
        temporary = result.with_name(result.name + ".tmp")
        temporary.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, result)
        print(
            "W032_CFG_LAYOUT_PASS cases=8 relro_cases=4 "
            "metadata_segment_cases=6 shared_metadata_segment_cases=2"
        )
        return 0
    except (LayoutError, OSError, UnicodeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"W032_CFG_LAYOUT_FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
