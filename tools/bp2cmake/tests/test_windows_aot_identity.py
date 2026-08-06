from dataclasses import replace
import json

import pytest

from tools import windows_aot_identity


def test_contract_pins_single_component_relocatable_identity():
    record = windows_aot_identity.contract_record()

    assert record == {
        "version": 1,
        "target_id": "windows-x86_64-msvc",
        "instruction_set": "x86_64",
        "component_topology": "single",
        "components": ["boot"],
        "boot_class_path_locations": ["/system/framework/boot.jar"],
        "boot_class_path_text": "/system/framework/boot.jar",
        "package_boot_jar": "runtime/boot.jar",
        "startup_image_location": "runtime/boot-image/boot.art",
        "package_image_files": [
            "runtime/boot-image/x86_64/boot.art",
            "runtime/boot-image/x86_64/boot.oat",
            "runtime/boot-image/x86_64/boot.vdex",
        ],
    }
    assert windows_aot_identity.generation_options() == (
        "--dex-location=/system/framework/boot.jar",
        "-Xbootclasspath-locations:/system/framework/boot.jar",
    )
    assert windows_aot_identity.startup_options() == (
        "-Xbootclasspath-locations:/system/framework/boot.jar",
        "-Ximage:runtime/boot-image/boot.art",
    )


@pytest.mark.parametrize(
    ("startup", "field"),
    [
        (
            replace(
                windows_aot_identity.CANONICAL_IDENTITY,
                boot_class_path_locations=("/System/framework/boot.jar",),
            ),
            "boot-class-path",
        ),
        (
            replace(
                windows_aot_identity.CANONICAL_IDENTITY,
                image_location=r"runtime\boot-image\boot.art",
            ),
            "image-location",
        ),
        (
            replace(
                windows_aot_identity.CANONICAL_IDENTITY,
                components=("boot", "boot-framework"),
            ),
            "component-topology",
        ),
    ],
)
def test_identity_comparison_is_byte_exact(startup, field):
    with pytest.raises(windows_aot_identity.WindowsAotIdentityError) as caught:
        windows_aot_identity.validate_generation_startup(
            windows_aot_identity.CANONICAL_IDENTITY,
            startup,
        )
    assert caught.value.field == field
    assert "mismatch" in str(caught.value)


def test_gate_records_all_intentional_mismatch_diagnostics(tmp_path):
    result = windows_aot_identity.run_gate(
        "windows-x86_64-msvc", tmp_path / "result.json"
    )
    record = json.loads(result.read_text(encoding="utf-8"))

    assert record["byte_exact_match"] is True
    assert len(record["rejected_mismatches"]) == 7
    assert {item["field"] for item in record["rejected_mismatches"]} == {
        "boot-class-path",
        "image-location",
        "component-topology",
    }


def test_gate_rejects_another_target(tmp_path):
    with pytest.raises(
        windows_aot_identity.WindowsAotIdentityError, match="accepts only"
    ):
        windows_aot_identity.run_gate(
            "windows-aarch64-msvc", tmp_path / "result.json"
        )
