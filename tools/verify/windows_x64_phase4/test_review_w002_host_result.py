#!/usr/bin/env python3
"""Unit tests for deterministic W-002 OSR and returned-evidence contracts."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import re
import tempfile
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parents[2]
SPEC = importlib.util.spec_from_file_location(
    "review_w002_host_result", SCRIPT_DIR / "review_w002_host_result.py"
)
assert SPEC is not None and SPEC.loader is not None
REVIEWER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REVIEWER)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class IssuedPayloadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="w002-review-test-")
        root = Path(self.temporary.name)
        self.issued = root / "issued"
        self.returned = root / "returned"
        self.issued.mkdir()
        self.returned.mkdir()
        self.payload = {
            "README_HOST.md": b"issued readme\n",
            "art.dll": b"issued art\n",
        }
        identities = {
            "BUILD_INFO.txt": b"build identity\n",
            "MANIFEST.json": b'{"identity": true}\n',
            "W002_STRUCTURAL_REPORT.txt": b"status=PASS\n",
        }
        sums = {
            **identities,
            **self.payload,
        }
        identities["SHA256SUMS.txt"] = "".join(
            f"{digest(data)}  ./{relative}\n"
            for relative, data in sorted(sums.items())
        ).encode()
        for relative, data in identities.items():
            (self.issued / relative).write_bytes(data)
            (self.returned / relative).write_bytes(data)
        for relative, data in self.payload.items():
            (self.issued / relative).write_bytes(data)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_accepts_evidence_only_return(self) -> None:
        self.assertEqual(
            REVIEWER.verify_issued_payload(self.returned, self.issued),
            "evidence-only",
        )

    def test_accepts_and_hashes_complete_payload(self) -> None:
        for relative, data in self.payload.items():
            (self.returned / relative).write_bytes(data)
        self.assertEqual(
            REVIEWER.verify_issued_payload(self.returned, self.issued),
            "full-package",
        )

    def test_rejects_changed_identity(self) -> None:
        (self.returned / "BUILD_INFO.txt").write_text(
            "different\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(RuntimeError, "BUILD_INFO.txt does not match"):
            REVIEWER.verify_issued_payload(self.returned, self.issued)

    def test_rejects_partial_payload(self) -> None:
        (self.returned / "art.dll").write_bytes(self.payload["art.dll"])
        with self.assertRaisesRegex(RuntimeError, "partial issued payload"):
            REVIEWER.verify_issued_payload(self.returned, self.issued)

    def test_rejects_changed_complete_payload(self) -> None:
        for relative, data in self.payload.items():
            (self.returned / relative).write_bytes(data)
        (self.returned / "art.dll").write_bytes(b"changed art\n")
        with self.assertRaisesRegex(RuntimeError, "changed issued file: art.dll"):
            REVIEWER.verify_issued_payload(self.returned, self.issued)


class OsrContractTest(unittest.TestCase):
    def test_probe_checksum_matches_declared_workload(self) -> None:
        source = (REPO / "tests/cases/osr-unwind/W002OsrProbe.java").read_text(
            encoding="utf-8"
        )
        count_match = re.search(r"COUNT = ([0-9_]+);", source)
        expected_match = re.search(r"EXPECTED = ([0-9_]+)L;", source)
        self.assertIsNotNone(count_match)
        self.assertIsNotNone(expected_match)
        count = int(count_match.group(1).replace("_", ""))
        expected = int(expected_match.group(1).replace("_", ""))
        actual = sum(((i * 17) ^ (i >> 3)) & 0xFFFF for i in range(count))
        self.assertEqual(count, 2_000_000)
        self.assertEqual(actual, expected)

    def test_unified_osr_runner_pins_both_thresholds(self) -> None:
        runner = REPO / "tests/support/windows/w002_managed_entry_gate.py"
        text = runner.read_text(encoding="utf-8")
        self.assertIn("-Xjitwarmupthreshold:100", text)
        self.assertIn("-Xjitthreshold:100", text)
        self.assertIn("checksum=65553463744", text)


if __name__ == "__main__":
    unittest.main()
