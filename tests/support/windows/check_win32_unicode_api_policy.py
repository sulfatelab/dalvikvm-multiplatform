#!/usr/bin/env python3
"""Inventory or reject explicit ANSI Win32 calls in active Windows sources."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys


# This is the reviewed W-027 migration inventory.  Keeping the API names
# explicit avoids confusing JNI's Call*MethodA family and ART/ICU helpers with
# Win32's encoding-selecting A/W entry points.
ANSI_WIN32_CALLS = frozenset(
    {
        "CreateDirectoryA",
        "CreateEventA",
        "CreateFileA",
        "CreateProcessA",
        "DeleteFileA",
        "FindFirstFileA",
        "FindNextFileA",
        "FormatMessageA",
        "GetComputerNameA",
        "GetCurrentDirectoryA",
        "GetEnvironmentVariableA",
        "GetFileAttributesA",
        "GetFullPathNameA",
        "GetModuleFileNameA",
        "GetModuleHandleA",
        "GetModuleHandleExA",
        "GetTempFileNameA",
        "GetTempPathA",
        "LoadLibraryA",
        "SetEnvironmentVariableA",
        "SetFileAttributesA",
        "gai_strerrorA",
    }
)

# Every other suffix-A call in the current Windows compilation graph is
# intentionally classified.  A new unclassified suffix-A call fails policy,
# so a newly introduced ANSI API cannot bypass the curated Win32 set merely by
# using a family name that W-027 did not encounter.
NON_WIN32_SUFFIX_A_CALLS = frozenset(
    {
        "BA",
        "CFA",
        "CFI_DEF_CFA",
        "CMSG_DATA",
        "COMMA",
        "CallBooleanMethodA",
        "CallByteMethodA",
        "CallCharMethodA",
        "CallDoubleMethodA",
        "CallFloatMethodA",
        "CallIntMethodA",
        "CallLongMethodA",
        "CallMethodA",
        "CallNonvirtualBooleanMethodA",
        "CallNonvirtualByteMethodA",
        "CallNonvirtualCharMethodA",
        "CallNonvirtualDoubleMethodA",
        "CallNonvirtualFloatMethodA",
        "CallNonvirtualIntMethodA",
        "CallNonvirtualLongMethodA",
        "CallNonvirtualObjectMethodA",
        "CallNonvirtualShortMethodA",
        "CallNonvirtualVoidMethodA",
        "CallObjectMethodA",
        "CallShortMethodA",
        "CallStaticBooleanMethodA",
        "CallStaticByteMethodA",
        "CallStaticCharMethodA",
        "CallStaticDoubleMethodA",
        "CallStaticFloatMethodA",
        "CallStaticIntMethodA",
        "CallStaticLongMethodA",
        "CallStaticObjectMethodA",
        "CallStaticShortMethodA",
        "CallStaticVoidMethodA",
        "CallVoidMethodA",
        "ConstructSubgraphClosedSSA",
        "DECLARE_LMBCS_DATA",
        "DFA",
        "ERA",
        "EVP_PKEY_assign_DSA",
        "EVP_PKEY_assign_RSA",
        "EVP_PKEY_get0_DSA",
        "EVP_PKEY_get0_RSA",
        "EVP_PKEY_get1_DSA",
        "EVP_PKEY_get1_RSA",
        "EVP_PKEY_set1_DSA",
        "EVP_PKEY_set1_RSA",
        "FMA",
        "FindMethodFromCHA",
        "GetVerifyTypeArgumentA",
        "IDNA",
        "ISALPHA",
        "LABEL_IDNA",
        "LOG_PRI_VA",
        "LZMA2_CONTROL_LZMA",
        "MA",
        "MethodA",
        "NewObjectA",
        "OPENSSL_MSVC_PRAGMA",
        "RETURN_VOID_IF_NOT_VALID_PARA",
        "SKIP_DATA",
        "TryInlineFromCHA",
        "UBIDI_GET_MIRROR_DELTA",
        "UCASE_GET_DELTA",
        "UCNV_EXT_FROM_U_GET_DATA",
        "VRegA",
        "moonA",
        "mul_A",
        "ucol_swapInverseUCA",
        "uprv_decNumberFMA",
        "vAA",
    }
)

SUFFIX_A_CALL = re.compile(r"\b([A-Za-z_]\w*A)\s*\(")
SOURCE_SUFFIXES = frozenset({".c", ".cc", ".cpp", ".cxx", ".s", ".S"})
RAW_STRING_START = re.compile(r'(?:u8|u|U|L)?R"([^\s()\\]{0,16})\(')


def fail(message: str) -> None:
    raise RuntimeError(message)


def _blank_non_newlines(characters: list[str], begin: int, end: int) -> None:
    for index in range(begin, end):
        if characters[index] not in "\r\n":
            characters[index] = " "


def scrub_c_family_literals_and_comments(text: str) -> str:
    """Replace comments and literals with spaces while preserving line layout."""

    characters = list(text)
    cursor = 0
    while cursor < len(text):
        raw = RAW_STRING_START.match(text, cursor)
        if raw is not None:
            terminator = ")" + raw.group(1) + '"'
            end = text.find(terminator, raw.end())
            end = len(text) if end < 0 else end + len(terminator)
            _blank_non_newlines(characters, cursor, end)
            cursor = end
            continue
        if text.startswith("//", cursor):
            end = text.find("\n", cursor + 2)
            end = len(text) if end < 0 else end
            _blank_non_newlines(characters, cursor, end)
            cursor = end
            continue
        if text.startswith("/*", cursor):
            end = text.find("*/", cursor + 2)
            end = len(text) if end < 0 else end + 2
            _blank_non_newlines(characters, cursor, end)
            cursor = end
            continue
        if text[cursor] in {'"', "'"}:
            quote = text[cursor]
            end = cursor + 1
            while end < len(text):
                if text[end] == "\\":
                    end = min(end + 2, len(text))
                    continue
                if text[end] == quote:
                    end += 1
                    break
                end += 1
            _blank_non_newlines(characters, cursor, end)
            cursor = end
            continue
        cursor += 1
    return "".join(characters)


def find_suffix_a_calls(text: str, relative: str) -> list[dict[str, object]]:
    scrubbed = scrub_c_family_literals_and_comments(text)
    findings: list[dict[str, object]] = []
    for match in SUFFIX_A_CALL.finditer(scrubbed):
        line_begin = scrubbed.rfind("\n", 0, match.start()) + 1
        findings.append(
            {
                "path": relative,
                "line": scrubbed.count("\n", 0, match.start()) + 1,
                "column": match.start() - line_begin + 1,
                "name": match.group(1),
            }
        )
    return findings


def active_sources(repo: Path, compile_commands: Path) -> list[tuple[str, Path]]:
    try:
        records = json.loads(compile_commands.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"cannot read compile database {compile_commands}: {error}")
    if not isinstance(records, list):
        fail(f"compile database is not a JSON list: {compile_commands}")

    repo = repo.resolve()
    binary_dir = compile_commands.resolve().parent
    sources: dict[str, Path] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("file"), str):
            fail("compile database contains a record without a string file field")
        path = Path(record["file"])
        if not path.is_absolute():
            directory = record.get("directory")
            if not isinstance(directory, str):
                fail("relative compile-database file has no string directory field")
            path = Path(directory) / path
        path = path.resolve()
        if path.suffix not in SOURCE_SUFFIXES:
            continue
        try:
            path.relative_to(binary_dir)
            continue
        except ValueError:
            pass
        try:
            relative = path.relative_to(repo).as_posix()
        except ValueError:
            continue
        sources.setdefault(relative, path)
    return sorted(sources.items())


def inspect_active_graph(repo: Path, compile_commands: Path) -> dict[str, object]:
    findings: list[dict[str, object]] = []
    sources = active_sources(repo, compile_commands)
    for relative, path in sources:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            fail(f"cannot read active source {relative}: {error}")
        findings.extend(find_suffix_a_calls(text, relative))

    ansi = [finding for finding in findings if finding["name"] in ANSI_WIN32_CALLS]
    unclassified = [
        finding
        for finding in findings
        if finding["name"] not in ANSI_WIN32_CALLS
        and finding["name"] not in NON_WIN32_SUFFIX_A_CALLS
    ]
    return {
        "active_source_count": len(sources),
        "suffix_a_call_count": len(findings),
        "ansi_call_count": len(ansi),
        "ansi_source_count": len({finding["path"] for finding in ansi}),
        "ansi_api_count": len({finding["name"] for finding in ansi}),
        "unclassified_call_count": len(unclassified),
        "ansi_findings": ansi,
        "unclassified_findings": unclassified,
    }


def finding_label(finding: dict[str, object]) -> str:
    return (
        f"{finding['path']}:{finding['line']}:{finding['column']}:"
        f"{finding['name']}"
    )


def check_policy(record: dict[str, object]) -> None:
    problems = [
        *(finding_label(finding) for finding in record["ansi_findings"]),
        *(finding_label(finding) for finding in record["unclassified_findings"]),
    ]
    if problems:
        fail("explicit ANSI or unclassified suffix-A calls remain:\n" + "\n".join(problems))


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--compile-commands", type=Path, required=True)
    parser.add_argument(
        "--inventory",
        action="store_true",
        help="print the migration inventory without enforcing zero findings",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        record = inspect_active_graph(args.repo, args.compile_commands)
        if not args.inventory:
            check_policy(record)
    except RuntimeError as error:
        print(f"win32-unicode-api-policy: FAIL: {error}", file=sys.stderr)
        return 1

    if args.inventory:
        print(json.dumps(record, indent=2, sort_keys=True))
    else:
        print(
            "win32-unicode-api-policy: PASS "
            f"active_sources={record['active_source_count']} "
            f"suffix_a_calls={record['suffix_a_call_count']} ansi_calls=0 "
            "unclassified_calls=0"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
