#!/usr/bin/env python3
"""Define and validate the boot-only Windows AOT location contract."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
from pathlib import Path, PurePosixPath
import sys
from typing import NoReturn


CONTRACT_VERSION = 1
TARGET_ID = "windows-x86_64-msvc"
INSTRUCTION_SET = "x86_64"
BOOT_COMPONENTS = ("boot",)
LOGICAL_BOOT_JAR = "/system/framework/boot.jar"
PACKAGE_BOOT_JAR = "runtime/boot.jar"
STARTUP_IMAGE_LOCATION = "runtime/boot-image/boot.art"
PACKAGE_IMAGE_FILES = tuple(
    f"runtime/boot-image/{INSTRUCTION_SET}/boot.{extension}"
    for extension in ("art", "oat", "vdex")
)
LOGICAL_PROBE_INPUT_JAR = "/data/local/tmp/win32-oat-probe.jar"
LOGICAL_PROBE_OAT = "probe.oat"


class WindowsAotIdentityError(RuntimeError):
    """Generation and startup disagree with the Windows AOT identity contract."""

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field


@dataclass(frozen=True)
class IdentityUse:
    """The strings consumed by one side of the generation/startup boundary."""

    boot_class_path_locations: tuple[str, ...]
    image_location: str
    components: tuple[str, ...]


CANONICAL_IDENTITY = IdentityUse(
    boot_class_path_locations=(LOGICAL_BOOT_JAR,),
    image_location=STARTUP_IMAGE_LOCATION,
    components=BOOT_COMPONENTS,
)


def contract_record() -> dict[str, object]:
    """Return the immutable, path-independent contract for manifests."""
    return {
        "version": CONTRACT_VERSION,
        "target_id": TARGET_ID,
        "instruction_set": INSTRUCTION_SET,
        "component_topology": "single",
        "components": list(BOOT_COMPONENTS),
        "boot_class_path_locations": list(CANONICAL_IDENTITY.boot_class_path_locations),
        "boot_class_path_text": _boot_class_path_text(CANONICAL_IDENTITY),
        "package_boot_jar": PACKAGE_BOOT_JAR,
        "startup_image_location": STARTUP_IMAGE_LOCATION,
        "package_image_files": list(PACKAGE_IMAGE_FILES),
    }


def generation_options() -> tuple[str, ...]:
    """Return the logical arguments that generation must record."""
    return (
        f"--dex-location={LOGICAL_BOOT_JAR}",
        f"-Xbootclasspath-locations:{_boot_class_path_text(CANONICAL_IDENTITY)}",
    )


def startup_options() -> tuple[str, ...]:
    """Return the package-relative identity arguments for the future launcher."""
    return (
        f"-Xbootclasspath-locations:{_boot_class_path_text(CANONICAL_IDENTITY)}",
        f"-Ximage:{STARTUP_IMAGE_LOCATION}",
    )


def validate_generation_startup(
    generation: IdentityUse,
    startup: IdentityUse,
) -> None:
    """Require byte-exact identity without path normalization or case folding."""
    comparisons = (
        (
            "boot-class-path",
            generation.boot_class_path_locations,
            startup.boot_class_path_locations,
        ),
        ("image-location", generation.image_location, startup.image_location),
        ("component-topology", generation.components, startup.components),
    )
    for field, generated, loaded in comparisons:
        if generated != loaded:
            raise WindowsAotIdentityError(
                field,
                f"{field} mismatch: generation={generated!r}, startup={loaded!r}",
            )
    if generation != CANONICAL_IDENTITY:
        raise WindowsAotIdentityError(
            "canonical-contract",
            f"matching generation/startup identity is not canonical: {generation!r}",
        )


def run_gate(target_id: str, result_path: Path) -> Path:
    """Exercise the canonical pair and a matrix of intentional mismatches."""
    if target_id != TARGET_ID:
        raise WindowsAotIdentityError(
            "target-id", f"identity contract accepts only {TARGET_ID}, got {target_id!r}"
        )

    validate_generation_startup(CANONICAL_IDENTITY, CANONICAL_IDENTITY)
    mismatch_cases = (
        (
            "boot-location-case",
            replace(
                CANONICAL_IDENTITY,
                boot_class_path_locations=("/System/framework/boot.jar",),
            ),
            "boot-class-path",
        ),
        (
            "boot-location-separator",
            replace(
                CANONICAL_IDENTITY,
                boot_class_path_locations=(r"\system\framework\boot.jar",),
            ),
            "boot-class-path",
        ),
        (
            "boot-location-physical",
            replace(
                CANONICAL_IDENTITY,
                boot_class_path_locations=("C:/package/runtime/boot.jar",),
            ),
            "boot-class-path",
        ),
        (
            "image-location-case",
            replace(CANONICAL_IDENTITY, image_location="Runtime/boot-image/boot.art"),
            "image-location",
        ),
        (
            "image-location-separator",
            replace(CANONICAL_IDENTITY, image_location=r"runtime\boot-image\boot.art"),
            "image-location",
        ),
        (
            "image-location-physical",
            replace(
                CANONICAL_IDENTITY,
                image_location="C:/package/runtime/boot-image/boot.art",
            ),
            "image-location",
        ),
        (
            "extra-component",
            replace(CANONICAL_IDENTITY, components=("boot", "boot-framework")),
            "component-topology",
        ),
    )
    rejected: list[dict[str, str]] = []
    for name, startup, expected_field in mismatch_cases:
        try:
            validate_generation_startup(CANONICAL_IDENTITY, startup)
        except WindowsAotIdentityError as exc:
            if exc.field != expected_field:
                _gate_bug(
                    f"{name} reported {exc.field!r}, expected {expected_field!r}"
                )
            rejected.append(
                {"case": name, "field": exc.field, "diagnostic": str(exc)}
            )
        else:
            _gate_bug(f"intentional mismatch was accepted: {name}")

    result_path = Path(result_path)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": 1,
        "target_id": target_id,
        "contract": contract_record(),
        "generation_options": list(generation_options()),
        "startup_options": list(startup_options()),
        "byte_exact_match": True,
        "rejected_mismatches": rejected,
    }
    result_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "Windows AOT identity contract passed: "
        f"components={len(BOOT_COMPONENTS)}, mismatches={len(rejected)}"
    )
    return result_path


def _boot_class_path_text(identity: IdentityUse) -> str:
    return ":".join(identity.boot_class_path_locations)


def _validate_static_contract() -> None:
    if BOOT_COMPONENTS != ("boot",):
        _gate_bug("the initial Windows AOT topology must have one boot component")
    for location in CANONICAL_IDENTITY.boot_class_path_locations:
        if (
            not location.isascii()
            or not PurePosixPath(location).is_absolute()
            or "\\" in location
            or ":" in location
        ):
            _gate_bug(f"invalid logical boot-class-path location: {location!r}")
    image = PurePosixPath(STARTUP_IMAGE_LOCATION)
    if (
        not STARTUP_IMAGE_LOCATION.isascii()
        or image.is_absolute()
        or "\\" in STARTUP_IMAGE_LOCATION
        or ":" in STARTUP_IMAGE_LOCATION
        or any(part in ("", ".", "..") for part in image.parts)
        or image.suffix != ".art"
    ):
        _gate_bug(f"invalid package-relative image location: {STARTUP_IMAGE_LOCATION!r}")
    if PACKAGE_IMAGE_FILES != (
        "runtime/boot-image/x86_64/boot.art",
        "runtime/boot-image/x86_64/boot.oat",
        "runtime/boot-image/x86_64/boot.vdex",
    ):
        _gate_bug("package image files do not match the single-component x86-64 topology")


def _gate_bug(message: str) -> NoReturn:
    raise WindowsAotIdentityError("gate-contract", message)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--result", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        run_gate(args.target_id, args.result)
        return 0
    except (OSError, WindowsAotIdentityError) as exc:
        print(f"windows_aot_identity.py: error: {exc}", file=sys.stderr)
        return 2


_validate_static_contract()


if __name__ == "__main__":
    raise SystemExit(main())
