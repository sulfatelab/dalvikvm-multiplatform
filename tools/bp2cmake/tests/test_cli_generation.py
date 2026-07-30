import json

from bp2cmake.__main__ import main


def _fixture(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    blueprint = source / "Android.bp"
    blueprint.write_text(
        'cc_library_shared { name: "libsample", srcs: ["sample.cc"] }\n',
        encoding="utf-8",
    )
    (source / "sample.cc").write_text("int sample;\n", encoding="utf-8")
    factory = tmp_path / "factory.py"
    factory.write_text(
        "from bp2cmake.overlay import Overlay\n"
        "def make_overlay(target):\n"
        "    return Overlay()\n",
        encoding="utf-8",
    )
    return source, blueprint, factory


def test_target_generation_writes_relocatable_graph_and_manifest(tmp_path):
    source, _blueprint, factory = _fixture(tmp_path)
    generated = tmp_path / "out" / "art_graph.cmake"
    manifest = tmp_path / "out" / "graph_manifest.json"
    profile = tmp_path / "out" / "target_profile.cmake"
    args = [
        "--root",
        str(source),
        "--overlay-factory",
        str(factory),
        "--target-id",
        "linux-x86_64",
        "--module",
        "libsample",
        "--out",
        str(generated),
        "--manifest-out",
        str(manifest),
        "--profile-out",
        str(profile),
    ]
    assert main(args) == 0

    graph_text = generated.read_text(encoding="utf-8")
    assert "add_library(sample SHARED" in graph_text
    assert "${MDVM_NATIVE_SRC_ROOT_DIR}/sample.cc" in graph_text
    assert str(source) not in graph_text

    graph_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    assert graph_manifest["target"]["target_id"] == "linux-x86_64"
    assert graph_manifest["modules"][0]["cmake_target"] == "sample"
    assert graph_manifest["blueprint_inputs"][0]["path"] == "Android.bp"
    assert str(source) not in manifest.read_text(encoding="utf-8")

    profile_text = profile.read_text(encoding="utf-8")
    assert 'set(ART_TARGET_ID "linux-x86_64")' in profile_text
    assert str(source) not in profile_text
    assert main(args + ["--check"]) == 0


def test_check_detects_stale_output_without_rewriting(tmp_path):
    source, blueprint, factory = _fixture(tmp_path)
    generated = tmp_path / "out" / "art_graph.cmake"
    base_args = [
        "--root",
        str(source),
        "--overlay-factory",
        str(factory),
        "--target-id",
        "linux-x86_64",
        "--module",
        "libsample",
        "--out",
        str(generated),
    ]
    assert main(base_args) == 0
    original = generated.read_bytes()
    blueprint.write_text(
        'cc_library_shared { name: "libsample", srcs: ["sample.cc"], cflags: ["-O2"] }\n',
        encoding="utf-8",
    )
    assert main(base_args + ["--check"]) == 2
    assert generated.read_bytes() == original


def test_planned_target_is_rejected_before_loading_sources(tmp_path):
    source, _blueprint, factory = _fixture(tmp_path)
    assert main(
        [
            "--root",
            str(source),
            "--overlay-factory",
            str(factory),
            "--target-id",
            "linux-riscv64",
            "--module",
            "libsample",
        ]
    ) == 2
