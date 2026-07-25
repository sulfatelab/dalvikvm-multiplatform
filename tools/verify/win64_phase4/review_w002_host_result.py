#!/usr/bin/env python3
"""Review returned native-Windows W-002 evidence against the issued package."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import sys
import tempfile
import zipfile


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_extract(archive: Path, output: Path) -> None:
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            target = (output / member.filename).resolve()
            if output.resolve() not in target.parents and target != output.resolve():
                fail(f"archive contains an unsafe path: {member.filename}")
        source.extractall(output)


def find_package_root(root: Path, required: str) -> Path:
    if (root / required).is_file():
        return root
    required_path = Path(required)
    candidates = sorted(
        path.parents[len(required_path.parts) - 1]
        for path in root.rglob(required_path.name)
        if path.as_posix().endswith(required_path.as_posix())
    )
    if len(candidates) != 1:
        fail(f"expected one package root containing {required}, found {len(candidates)}")
    return candidates[0]


def read_sums(path: Path) -> dict[str, str]:
    sums: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            fail(f"invalid SHA256SUMS line: {line!r}")
        relative = match.group(2)
        if relative.startswith("./"):
            relative = relative[2:]
        sums[Path(relative).as_posix()] = match.group(1)
    return sums


def verify_issued_payload(returned: Path, issued: Path) -> None:
    if (returned / "SHA256SUMS.txt").read_bytes() != (
        issued / "SHA256SUMS.txt"
    ).read_bytes():
        fail("returned SHA256SUMS.txt does not match the issued package")
    issued_sums = read_sums(issued / "SHA256SUMS.txt")
    for relative, expected in issued_sums.items():
        path = returned / relative
        if not path.is_file():
            fail(f"returned package is missing issued file: {relative}")
        if sha256(path) != expected:
            fail(f"returned package changed issued file: {relative}")


def require_markers(path: Path, markers: list[str], forbidden: list[str] | None = None) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    for marker in markers:
        if marker not in text:
            fail(f"{path.name} is missing marker: {marker}")
    for marker in forbidden or []:
        if marker in text:
            fail(f"{path.name} contains forbidden marker: {marker}")


def expected_case_names() -> list[str]:
    names: list[str] = []
    for mode in ("dual", "j1"):
        for interpreter in ("default", "switch"):
            for repeat in range(1, 3):
                names.append(f"osr_{mode}_{interpreter}_run{repeat:02d}")
                names.append(f"attach_{mode}_{interpreter}_run{repeat:02d}")
    return names


def review(returned: Path, issued: Path) -> None:
    verify_issued_payload(returned, issued)
    logs = returned / "logs"
    if not logs.is_dir():
        fail("returned package has no logs directory")

    result_path = logs / "RESULT_W002.txt"
    if not result_path.is_file():
        fail("RESULT_W002.txt is missing")
    result_lines = result_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not result_lines or result_lines[-1] != "OVERALL PASS":
        fail("RESULT_W002.txt does not end with OVERALL PASS")
    if any(line.startswith("FAIL ") or line == "OVERALL FAIL" for line in result_lines):
        fail("RESULT_W002.txt contains a failure record")

    required_result_prefixes = [
        "PASS host_os build=",
        "PASS package_integrity",
        "PASS structural_report",
        *[f"PASS {name} exit=0 " for name in expected_case_names()],
        "PASS log_scan",
        "PASS dump_scan NO_DMP_FILES",
    ]
    for prefix in required_result_prefixes:
        if not any(line.startswith(prefix) for line in result_lines):
            fail(f"RESULT_W002.txt is missing result: {prefix}")
    pass_lines = [line for line in result_lines if line.startswith("PASS ")]
    if len(pass_lines) != 21:
        fail(f"expected 21 PASS records, found {len(pass_lines)}")

    windows_version = logs / "WINDOWS_VERSION.txt"
    require_markers(windows_version, ["BuildNumber", "OSArchitecture"])
    version_text = windows_version.read_text(encoding="utf-8", errors="replace")
    build_match = re.search(r"BuildNumber\s*:\s*(\d+)", version_text)
    if build_match is None or int(build_match.group(1)) < 17134:
        fail("native result does not prove Windows 10 RS4 build 17134 or later")

    copied_report = logs / "W002_STRUCTURAL_REPORT.txt"
    if not copied_report.is_file():
        fail("returned logs do not contain W002_STRUCTURAL_REPORT.txt")
    if copied_report.read_bytes() != (issued / "W002_STRUCTURAL_REPORT.txt").read_bytes():
        fail("returned structural report does not match the issued report")

    osr_common = [
        "exit=0",
        "timed_out=False",
        "W002OsrProbe OK checksum=9835131152",
        "kind=Baseline",
        "kind=Osr",
        "Jumping to long W002OsrProbe.osrLoop(int)",
        "main end exception=0",
    ]
    attach_common = [
        "exit=0",
        "timed_out=False",
        "W002AttachProbe OK completed=16",
        (
            "Win64 CompileMethod done success=1 method=long "
            "W002AttachProbe.attachedCallback(boolean, int)"
        ),
        "main end exception=0",
    ]
    switch_completion = (
        "Done running OSR code for long W002OsrProbe.osrLoop(int)"
    )
    for mode in ("dual", "j1"):
        for interpreter in ("default", "switch"):
            for repeat in range(1, 3):
                osr = logs / f"osr_{mode}_{interpreter}_run{repeat:02d}.log"
                attach = logs / f"attach_{mode}_{interpreter}_run{repeat:02d}.log"
                if interpreter == "switch":
                    require_markers(osr, [*osr_common, switch_completion])
                else:
                    require_markers(osr, osr_common, [switch_completion])
                require_markers(attach, attach_common)

    require_markers(logs / "DMP_SCAN.txt", ["NO_DMP_FILES"])
    bad_patterns = [
        "Check failed:",
        "Fatal signal",
        "Unhandled page fault",
        "Unhandled exception",
        "Access violation",
        "STATUS_ACCESS_VIOLATION",
        "0xc0000005",
    ]
    for log in logs.glob("*.log"):
        text = log.read_text(encoding="utf-8", errors="replace")
        for pattern in bad_patterns:
            if pattern in text:
                fail(f"{log.name} contains fatal marker: {pattern}")

    print(
        "W-002 native host result: PASS "
        f"(build={build_match.group(1)}, cases=16, pass_records=21)"
    )


def materialize(path: Path, temporary: Path, required: str, label: str) -> Path:
    if path.is_dir():
        return find_package_root(path.resolve(), required)
    if not path.is_file() or not zipfile.is_zipfile(path):
        fail(f"not a package directory or ZIP archive: {path}")
    output = temporary / label
    output.mkdir()
    safe_extract(path, output)
    return find_package_root(output, required)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("returned", type=Path)
    parser.add_argument("--issued", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="w002-host-review-") as directory:
        temporary = Path(directory)
        returned = materialize(
            args.returned, temporary, "logs/RESULT_W002.txt", "returned"
        )
        issued = materialize(args.issued, temporary, "SHA256SUMS.txt", "issued")
        review(returned, issued)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as error:
        print(f"W-002 native host result: FAIL: {error}", file=sys.stderr)
        sys.exit(1)
