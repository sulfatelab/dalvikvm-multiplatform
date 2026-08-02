import json
from pathlib import Path

from bp2cmake.__main__ import _generate, _parser
from bp2cmake.config import Config
from bp2cmake.overlay import load_overlay_factory
from bp2cmake.target import resolve_target


def test_linux_aarch64_experimental_graph_uses_selected_architecture(tmp_path):
    repo = Path(__file__).resolve().parents[3]
    vendor = repo / "vendor"
    target = resolve_target("linux-aarch64-gnu")
    generated = tmp_path / "generated"
    arguments = [
        "--root",
        str(vendor),
        "--overlay-factory",
        str(repo / "overlay" / "art_port_policy.py"),
        "--target-id",
        target.target_id,
        "--extra-root",
        f"{vendor}:MDVM_ART_ROOT_DIR",
        "--extra-root",
        f"{vendor / 'libcore'}:MDVM_LIBCORE_DIR",
        "--extra-root",
        f"{vendor / 'icu'}:MDVM_ICU_DIR",
        "--extra-root",
        f"{vendor / 'java-external' / 'fdlibm'}:MDVM_FDLIBM_DIR",
    ]
    for module in (
        "dalvikvm",
        "dex2oat",
        "libart-compiler",
        "libjavacrypto",
        "libjavacore",
        "libopenjdk",
        "libicu_jni",
        "libopenjdkjvmti",
    ):
        arguments.extend(("--root-module", module))
    arguments.extend(
        (
            "--out",
            str(generated / "art_graph.cmake"),
            "--manifest-out",
            str(generated / "graph_manifest.json"),
            "--profile-out",
            str(generated / "target_profile.cmake"),
        )
    )
    parser = _parser()
    args = parser.parse_args(arguments)
    overlay = load_overlay_factory(args.overlay_factory, target)

    assert target.support_status == "experimental"
    assert _generate(args, parser, target, Config.from_target(target), overlay) == 0

    manifest = json.loads(
        (generated / "graph_manifest.json").read_text(encoding="utf-8")
    )
    sources = {
        source
        for module in manifest["modules"]
        for source in module.get("sources", [])
    }
    assert manifest["target"]["target_id"] == "linux-aarch64-gnu"
    assert len(manifest["modules"]) == 38
    modules = {module["aosp_name"]: module for module in manifest["modules"]}
    assert modules["libvixl"]["kind"] == "static"
    assert "vixl" in modules["libart-disassembler"]["link_dependencies"]
    assert (
        "${MDVM_ART_ROOT_DIR}/external/vixl/src"
        in modules["libart-disassembler"]["include_dirs"]
    )
    assert any("external/vixl/src/aarch64/" in source for source in sources)
    # ART's 64-bit ARM codegen deliberately includes its 32-bit sibling.
    assert any("external/vixl/src/aarch32/" in source for source in sources)
    assert any(source.endswith("quick_entrypoints_arm64.S") for source in sources)
    assert any(source.endswith("mterp_arm64.S") for source in sources)
    assert any("external/boringssl/linux-aarch64/" in source for source in sources)
    assert not any(source.endswith("quick_entrypoints_x86_64.S") for source in sources)
    assert not any("external/boringssl/linux-x86_64/" in source for source in sources)
