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
            REVIEWER.OSR_UNWIND_MARKERS[1],
            REVIEWER.OSR_UNWIND_MARKERS[3],
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

    def test_native_result_contract_has_thirty_records(self) -> None:
        self.assertEqual(REVIEWER.EXPECTED_PASS_RECORDS, 30)


class XmmLogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="w010-w014-xmm-log-")
        self.logs = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_log(
        self, name: str, mode: str, *, include_full_mask: bool = True
    ) -> None:
        lines = [
            f"W003XmmSentinelProbe mode={mode}",
            "mask=0 selfTestMask=63 iterations=128",
        ]
        if include_full_mask:
            lines.append("fullSelfTestMask=1023")
        lines.extend(("W003XmmSentinelProbe OK", "main end exception=0"))
        if mode == "jit":
            lines.append("success=1 method=int W003XmmSentinelProbe.managedCallback(")
        lines.extend(("exit=0", "timed_out=False"))
        (self.logs / f"{name}.log").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    def test_accepts_complete_jit_log(self) -> None:
        self.write_log("xmm_full_jit_run01", "jit")
        REVIEWER.review_xmm_log(self.logs, "xmm_full_jit_run01", "jit")

    def test_rejects_missing_full_width_self_test(self) -> None:
        self.write_log("xmm_full_nterp_run01", "nterp", include_full_mask=False)
        with self.assertRaisesRegex(RuntimeError, "fullSelfTestMask=1023"):
            REVIEWER.review_xmm_log(self.logs, "xmm_full_nterp_run01", "nterp")


class StackGuaranteeLogTest(unittest.TestCase):
    def test_accepts_minimum_and_preserved_larger_values(self) -> None:
        REVIEWER.review_stack_guarantees(
            "stack_guarantee label=main before=0 configured=16384 minimum=16384\n"
            "stack_guarantee label=pthread before=32768 configured=32768 minimum=16384\n"
        )

    def test_rejects_configured_value_below_minimum(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "below the minimum"):
            REVIEWER.review_stack_guarantees(
                "stack_guarantee label=main before=0 configured=8192 minimum=16384\n"
                "stack_guarantee label=pthread before=0 configured=16384 minimum=16384\n"
            )

    def test_rejects_reducing_existing_larger_value(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "did not preserve"):
            REVIEWER.review_stack_guarantees(
                "stack_guarantee label=main before=32768 configured=16384 minimum=16384\n"
                "stack_guarantee label=pthread before=0 configured=16384 minimum=16384\n"
            )


if __name__ == "__main__":
    unittest.main()
