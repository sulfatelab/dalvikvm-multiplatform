#!/usr/bin/env python3
"""Run one accepted libcore smoke case without shell tooling."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


_SUPPORT_ROOT = Path(__file__).parents[2] / "support"
if str(_SUPPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SUPPORT_ROOT))

import runtime_gate  # noqa: E402


_MATRIX_PATH = Path(__file__).with_name("runtime-matrix.json")
_COMMON_FORBIDDEN = [
    "AssertionError",
    "ART Win32 VEH",
    "ART Win32 UEF",
    "Check failed",
    "Fatal signal",
    "minidump written",
]


def load_matrix(path: Path = _MATRIX_PATH) -> dict[str, dict[str, object]]:
    path = runtime_gate._regular_file(str(path))
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise runtime_gate.GateError(f"invalid libcore matrix: {exc}") from exc
    if not isinstance(document, dict) or set(document) != {"schema_version", "cases"}:
        raise runtime_gate.GateError(
            "libcore matrix must contain exactly schema_version and cases"
        )
    if document["schema_version"] != 1:
        raise runtime_gate.GateError(
            f"unsupported libcore matrix schema: {document['schema_version']!r}"
        )
    raw_cases = document["cases"]
    if not isinstance(raw_cases, dict) or not raw_cases:
        raise runtime_gate.GateError("libcore matrix cases must be a non-empty object")

    allowed = {
        "expected_markers",
        "forbidden_markers",
        "mode",
        "require_nonzero",
        "timeout_seconds",
    }
    cases: dict[str, dict[str, object]] = {}
    for name, raw_case in raw_cases.items():
        if not isinstance(name, str) or not name.isidentifier():
            raise runtime_gate.GateError(f"invalid libcore main class: {name!r}")
        if not isinstance(raw_case, dict) or not set(raw_case) <= allowed:
            raise runtime_gate.GateError(f"libcore case {name} has unknown fields")
        expected = raw_case.get("expected_markers")
        forbidden = raw_case.get("forbidden_markers", [])
        mode = raw_case.get("mode", "managed")
        require_nonzero = raw_case.get("require_nonzero", False)
        timeout = raw_case.get("timeout_seconds")
        if not isinstance(expected, list) or not expected or not all(
            isinstance(marker, str) and marker for marker in expected
        ):
            raise runtime_gate.GateError(
                f"libcore case {name} expected markers must be non-empty strings"
            )
        if not isinstance(forbidden, list) or not all(
            isinstance(marker, str) and marker for marker in forbidden
        ):
            raise runtime_gate.GateError(
                f"libcore case {name} forbidden markers must be strings"
            )
        if not isinstance(require_nonzero, bool):
            raise runtime_gate.GateError(
                f"libcore case {name} require_nonzero must be boolean"
            )
        if mode not in {"managed", "path", "absolute-path"}:
            raise runtime_gate.GateError(
                f"libcore case {name} has unsupported mode: {mode!r}"
            )
        if mode != "managed" and require_nonzero:
            raise runtime_gate.GateError(
                f"libcore case {name} path mode cannot require nonzero"
            )
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 1:
            raise runtime_gate.GateError(
                f"libcore case {name} timeout_seconds must be a positive integer"
            )
        cases[name] = {
            "expected_markers": list(expected),
            "forbidden_markers": [*_COMMON_FORBIDDEN, *forbidden],
            "mode": mode,
            "require_nonzero": require_nonzero,
            "timeout_seconds": timeout,
        }
    return cases


def _copy_regular(source: Path, destination: Path) -> Path:
    source = runtime_gate._regular_file(str(source))
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return runtime_gate._regular_file(str(destination))


def _path_environment(runtime_root: Path, library_dirs: list[Path]) -> dict[str, str]:
    (runtime_root / "data").mkdir(parents=True)
    (runtime_root / "icu").mkdir()
    (runtime_root / "tmp").mkdir()
    environment = os.environ.copy()
    environment.update({
        "ANDROID_ROOT": str(runtime_root),
        "ANDROID_ART_ROOT": str(runtime_root),
        "ANDROID_I18N_ROOT": str(runtime_root),
        "ANDROID_DATA": str(runtime_root / "data"),
        "ICU_DATA": str(runtime_root / "icu"),
        "TMP": str(runtime_root / "tmp"),
        "TEMP": str(runtime_root / "tmp"),
        "TMPDIR": str(runtime_root / "tmp"),
    })
    checked_dirs = [runtime_gate._managed_path(path) for path in library_dirs]
    if os.name == "nt":
        system_root = environment.get("SystemRoot", r"C:\Windows")
        environment["PATH"] = os.pathsep.join(
            [*(str(path) for path in checked_dirs), str(Path(system_root) / "System32")]
        )
    else:
        environment["LD_LIBRARY_PATH"] = os.pathsep.join(
            str(path) for path in checked_dirs
        )
    return environment


def _execute_path_case(
    *,
    name: str,
    command: list[str],
    work_root: Path,
    environment: dict[str, str],
    expected: list[str],
    forbidden: list[str],
    timeout: int,
    require_nonzero: bool = False,
    expected_any: list[str] | None = None,
) -> tuple[dict[str, object], str | None, str]:
    case_root = work_root / "cases" / name
    case_root.mkdir(parents=True)
    try:
        result = subprocess.run(
            command,
            cwd=work_root,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            shell=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        record = {
            "name": name,
            "actual_exit": None,
            "timed_out": True,
            "missing_markers": list(expected),
            "forbidden_markers": [],
            "status": "FAIL",
        }
        return record, f"{name} timed out after {timeout} seconds", ""

    (case_root / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (case_root / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    combined = result.stdout + "\n" + result.stderr
    missing = [marker for marker in expected if marker not in combined]
    if expected_any and not any(marker in combined for marker in expected_any):
        missing.append("one-of:" + "|".join(expected_any))
    present_forbidden = [marker for marker in forbidden if marker in combined]
    exit_ok = result.returncode != 0 if require_nonzero else result.returncode == 0
    passed = exit_ok and not missing and not present_forbidden
    record = {
        "name": name,
        "actual_exit": result.returncode,
        "timed_out": False,
        "exit_contract": "nonzero" if require_nonzero else "zero",
        "missing_markers": missing,
        "forbidden_markers": present_forbidden,
        "status": "PASS" if passed else "FAIL",
    }
    if passed:
        return record, None, combined
    tail = "\n".join(combined.splitlines()[-80:])
    failure = (
        f"{name} failed: exit={result.returncode}, missing={missing}, "
        f"forbidden={present_forbidden}\n{tail}"
    )
    return record, failure, combined


def _path_probe_block_failures(output: str) -> list[str]:
    required_blocks = {
        "drive": ("in=C:\\x", "path=C:\\x", "prefixLength=3", "isAbsolute=true"),
        "mixed": (
            "in=C:\\User/admin/.ssh/x",
            "path=C:\\User\\admin\\.ssh\\x",
            "isAbsolute=true",
        ),
        "unc": (
            "in=\\\\server\\share\\a",
            "path=\\\\server\\share\\a",
            "isAbsolute=true",
        ),
    }
    blocks = output.split("---")
    return [
        label
        for label, markers in required_blocks.items()
        if not any(all(marker in block for marker in markers) for block in blocks)
    ]


def _run_path_gate(
    *,
    case: str,
    target_id: str,
    config: dict[str, object],
    dalvikvm: Path,
    boot_jar: Path,
    app_jar: Path,
    hello_jar: Path,
    path_jar: Path | None,
    work_root: Path,
    icu_data: Path,
    library_dirs: list[Path],
) -> None:
    dalvikvm = runtime_gate._regular_file(str(dalvikvm))
    work_root.mkdir(parents=True)
    boot = _copy_regular(boot_jar, work_root / "inputs" / "boot.jar")
    app = _copy_regular(app_jar, work_root / "run" / app_jar.name)
    hello = _copy_regular(hello_jar, work_root / "absolute" / "hello.jar")
    relative_hello = _copy_regular(hello_jar, work_root / "run" / "hello.jar")
    staged_path = app if case == "PathProbe" else _copy_regular(
        path_jar, work_root / "run" / "pathprobe.jar"
    )
    runtime_root = work_root / "runtime"
    environment = _path_environment(runtime_root, library_dirs)
    _copy_regular(icu_data, runtime_root / "icu" / icu_data.name)
    timeout = config["timeout_seconds"]
    forbidden = config["forbidden_markers"]
    base = [
        str(dalvikvm),
        f"-Xbootclasspath:{boot}",
        f"-Xbootclasspath-locations:{boot}",
        f"-Ximage:{runtime_root / 'nonexistent-boot-image'}",
        "-XjdwpProvider:none",
        "-Xint",
        "-Xms64m",
        "-Xmx512m",
    ]
    records: list[dict[str, object]] = []
    failures: list[str] = []

    def run(name: str, arguments: list[str], **contracts: object) -> str:
        case_forbidden = contracts.pop("forbidden", forbidden)
        record, failure, output = _execute_path_case(
            name=name,
            command=[*base, *arguments],
            work_root=work_root,
            environment=environment,
            timeout=timeout,
            forbidden=case_forbidden,
            **contracts,
        )
        records.append(record)
        if failure is not None:
            failures.append(failure)
        return output

    if case == "PathProbe":
        run(
            "hello-regression",
            ["-cp", str(relative_hello), "Hello"],
            expected=["Hello from dalvikvm!", "main end exception=0"],
        )
        output = run(
            "path-probe",
            ["-cp", f"{app};{relative_hello}", "PathProbe"],
            expected=config["expected_markers"],
        )
        block_failures = _path_probe_block_failures(output)
        if block_failures:
            records[-1]["status"] = "FAIL"
            records[-1]["missing_path_blocks"] = block_failures
            failures.append(f"PathProbe missing structured blocks: {block_failures}")
    else:
        backslash = str(hello)
        forward = backslash.replace("\\", "/")
        mixed = str(hello.parent) + "/hello.jar"
        for name, classpath in (
            ("absolute-forward", forward),
            ("absolute-backslash", backslash),
            ("absolute-mixed", mixed),
        ):
            run(
                name,
                ["-cp", classpath, "Hello"],
                expected=["Hello from dalvikvm!", "main end exception=0"],
            )
        run(
            "absolute-probe",
            ["-cp", f"{backslash};{app}", "AbsPathProbe", backslash],
            expected=config["expected_markers"],
        )
        run(
            "colon-relative-negative",
            ["-cp", "run/pathprobe.jar:run/hello.jar", "PathProbe"],
            expected=[],
            expected_any=["ClassNotFoundException", "Unable to locate class"],
            require_nonzero=True,
        )
        run(
            "colon-absolute-negative",
            ["-cp", f"{backslash}:{backslash}", "Hello"],
            expected=[],
            forbidden=[*forbidden, "Hello from dalvikvm!"],
            require_nonzero=True,
        )

    record = {
        "schema_version": 1,
        "target_id": target_id,
        "main_class": case,
        "boot_jar": {"name": boot.name, "sha256": runtime_gate._sha256(boot)},
        "app_jar": {"name": app.name, "sha256": runtime_gate._sha256(app)},
        "hello_jar": {
            "name": relative_hello.name,
            "sha256": runtime_gate._sha256(relative_hello),
        },
        "path_jar": {"name": staged_path.name, "sha256": runtime_gate._sha256(staged_path)},
        "completed_cases": sum(item["status"] == "PASS" for item in records),
        "requested_cases": len(records),
        "cases": records,
        "reparse_paths": [],
    }
    (work_root / "result.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    runtime_gate._reject_tree_links(work_root)
    if failures:
        raise runtime_gate.GateError(failures[0])
    print(f"{case} passed for {target_id}: cases={len(records)}")


def run_gate(
    *,
    case: str,
    target_id: str,
    dalvikvm: Path,
    boot_jar: Path,
    app_jar: Path,
    work_root: Path,
    icu_data: Path,
    library_dirs: list[Path],
    hello_jar: Path | None = None,
    path_jar: Path | None = None,
    cacerts_dir: Path | None = None,
    security_properties: Path | None = None,
    runner: Path | None = None,
    runner_args: list[str] | None = None,
) -> None:
    matrix = load_matrix()
    if case not in matrix:
        raise runtime_gate.GateError(f"unknown libcore case: {case}")
    config = matrix[case]

    work_root = runtime_gate._managed_path(work_root, allow_missing=True)
    if work_root.exists() or work_root.is_symlink():
        runtime_gate._reject_tree_links(work_root)
        shutil.rmtree(work_root)

    if config["mode"] == "managed":
        runtime_gate.run_managed(
            target_id=target_id,
            dalvikvm=dalvikvm,
            boot_jar=boot_jar,
            app_jar=app_jar,
            main_class=case,
            work_root=work_root,
            icu_data=icu_data,
            library_dirs=library_dirs,
            vm_options=["-Xint"],
            main_args=[],
            expected=config["expected_markers"],
            forbidden=config["forbidden_markers"],
            expected_exit=0,
            timeout=config["timeout_seconds"],
            require_nonzero=config["require_nonzero"],
            cacerts_dir=cacerts_dir,
            security_properties=security_properties,
            runner=runner,
            runner_args=runner_args,
        )
    else:
        if runner is not None or runner_args:
            raise runtime_gate.GateError(
                f"{case} path mode does not support a target runner"
            )
        if hello_jar is None:
            raise runtime_gate.GateError(f"{case} requires --hello-jar")
        if config["mode"] == "absolute-path" and path_jar is None:
            raise runtime_gate.GateError(f"{case} requires --path-jar")
        _run_path_gate(
            case=case,
            target_id=target_id,
            config=config,
            dalvikvm=dalvikvm,
            boot_jar=boot_jar,
            app_jar=app_jar,
            hello_jar=hello_jar,
            path_jar=path_jar,
            work_root=work_root,
            icu_data=icu_data,
            library_dirs=library_dirs,
        )
    runtime_gate._reject_tree_links(work_root)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--dalvikvm", type=Path, required=True)
    parser.add_argument("--boot-jar", type=Path, required=True)
    parser.add_argument("--app-jar", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--icu-data", type=Path, required=True)
    parser.add_argument("--library-dir", type=Path, action="append", default=[])
    parser.add_argument("--hello-jar", type=Path)
    parser.add_argument("--path-jar", type=Path)
    parser.add_argument("--cacerts-dir", type=Path)
    parser.add_argument("--security-properties", type=Path)
    parser.add_argument("--runner", type=runtime_gate._regular_file)
    parser.add_argument("--runner-arg", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        run_gate(
            case=args.case,
            target_id=args.target_id,
            dalvikvm=args.dalvikvm,
            boot_jar=args.boot_jar,
            app_jar=args.app_jar,
            work_root=args.work_root,
            icu_data=args.icu_data,
            library_dirs=args.library_dir,
            hello_jar=args.hello_jar,
            path_jar=args.path_jar,
            cacerts_dir=args.cacerts_dir,
            security_properties=args.security_properties,
            runner=args.runner,
            runner_args=args.runner_arg,
        )
        return 0
    except (runtime_gate.GateError, OSError, UnicodeError) as exc:
        print(f"windows-libcore-smoke/run.py: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
