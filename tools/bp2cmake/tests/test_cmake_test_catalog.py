import json
from pathlib import Path
import shutil
import subprocess

import pytest

from bp2cmake.target import resolve_target


def test_windows_catalog_configures_with_typed_identity_selectors(tmp_path):
    cmake = shutil.which("cmake")
    if cmake is None:
        pytest.skip("CMake is unavailable")

    repo = Path(__file__).resolve().parents[3]
    source = tmp_path / "source"
    binary = tmp_path / "build"
    source.mkdir()
    profile = source / "target_profile.cmake"
    profile.write_text(
        resolve_target("windows-x86_64-msvc").to_cmake(), encoding="utf-8"
    )
    cmake_lists = f"""
cmake_minimum_required(VERSION 3.16)
project(ArtTestCatalogFixture C CXX ASM)
include("{profile.as_posix()}")
set(ART_ENABLE_TARGET_RUNTIME_TESTS OFF)
set(ART_TARGET_BUNDLE_ROOT "{(tmp_path / 'bundle').as_posix()}")
set(MDVM_COMPAT_INCLUDE_DIR "{(repo / 'compat' / 'include').as_posix()}")
set(MDVM_GENSRC_DIR "{(tmp_path / 'gensrc').as_posix()}")
set(MDVM_NATIVE_SRC_ROOT_DIR "{(repo / 'vendor').as_posix()}")
set(_art_windows_cxx_include "")
set(_art_windows_system_includes "")
set(_art_windows_system_compile_options "")
set(_art_bundle_lib "{(tmp_path / 'bundle' / 'lib').as_posix()}")
add_library(art INTERFACE)
add_library(art_windows_cxx INTERFACE)
add_library(windows_x64_posix_stubs INTERFACE)
enable_testing()
add_subdirectory("{(repo / 'tests').as_posix()}" art-tests)
"""
    (source / "CMakeLists.txt").write_text(cmake_lists, encoding="utf-8")

    result = subprocess.run(
        [cmake, "-S", str(source), "-B", str(binary), "-G", "Ninja"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    catalog = json.loads(
        (binary / "art-tests" / "art_test_catalog.json").read_text(encoding="utf-8")
    )
    assert catalog["target_id"] == "windows-x86_64-msvc"
    assert len(catalog["probes"]) == 29
    assert sum(probe["applicable"] for probe in catalog["probes"]) == 29
    assert sum(bool(probe["target_ids"]) for probe in catalog["probes"]) == 10
    assert sum(not probe["target_ids"] for probe in catalog["probes"]) == 19
    assert sum(
        probe["execution"] == "target-runnable" for probe in catalog["probes"]
    ) == 3
    assert not any(probe["ctest_registered"] for probe in catalog["probes"])
