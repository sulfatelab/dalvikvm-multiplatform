#!/usr/bin/env python3
"""Unit tests for W-010/W-014 returned-evidence review contracts."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "review_w010_w014_host_result",
    SCRIPT_DIR / "review_w010_w014_host_result.py",
)
assert SPEC is not None and SPEC.loader is not None
REVIEWER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REVIEWER)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class IssuedPayloadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="w010-w014-review-test-")
        root = Path(self.temporary.name)
        self.issued = root / "issued"
        self.returned = root / "returned"
        self.issued.mkdir()
        self.returned.mkdir()
        self.payload = {
            "W010_W014_HOST_CHECKLIST.md": b"issued checklist\n",
            "art.dll": b"issued art\n",
        }
        identities = {
            "BUILD_INFO.txt": b"build identity\n",
            "MANIFEST.json": b'{"identity": true}\n',
            "W010_W014_STRUCTURAL_REPORT.txt": b"status=PASS\n",
        }
        sums = {**identities, **self.payload}
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

    def test_accepts_complete_unchanged_payload(self) -> None:
        for relative, data in self.payload.items():
            (self.returned / relative).write_bytes(data)
        self.assertEqual(
            REVIEWER.verify_issued_payload(self.returned, self.issued),
            "full-package",
        )

    def test_rejects_partial_payload(self) -> None:
        (self.returned / "art.dll").write_bytes(self.payload["art.dll"])
        with self.assertRaisesRegex(RuntimeError, "partial issued payload"):
            REVIEWER.verify_issued_payload(self.returned, self.issued)


class OsrUnwindLogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="w010-w014-osr-log-")
        self.logs = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_log(self, *lines: str) -> None:
        (self.logs / "osr_unwind.log").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    def test_accepts_complete_zero_exit_log(self) -> None:
        self.write_log(
            *REVIEWER.OSR_UNWIND_MARKERS,
            "exit=0",
            "timed_out=False",
        )
        REVIEWER.review_osr_log(self.logs)

    def test_rejects_missing_split_range_invariants(self) -> None:
        self.write_log(
            REVIEWER.OSR_UNWIND_MARKERS[0],
            REVIEWER.OSR_UNWIND_MARKERS[2],
            "exit=0",
            "timed_out=False",
        )
        with self.assertRaisesRegex(RuntimeError, "entry_frame_offset=0"):
            REVIEWER.review_osr_log(self.logs)

    def test_rejects_handled_fault_diagnostics(self) -> None:
        self.write_log(
            *REVIEWER.OSR_UNWIND_MARKERS,
            "ART Win64 VEH",
            "exit=0",
            "timed_out=False",
        )
        with self.assertRaisesRegex(RuntimeError, "forbidden marker"):
            REVIEWER.review_osr_log(self.logs)

    def test_rejects_nonzero_exit(self) -> None:
        self.write_log(
            *REVIEWER.OSR_UNWIND_MARKERS,
            "exit=5",
            "timed_out=False",
        )
        with self.assertRaisesRegex(RuntimeError, "nonzero exit=5"):
            REVIEWER.review_osr_log(self.logs)

    def test_native_result_contract_has_twenty_records(self) -> None:
        self.assertEqual(REVIEWER.EXPECTED_PASS_RECORDS, 20)


if __name__ == "__main__":
    unittest.main()
