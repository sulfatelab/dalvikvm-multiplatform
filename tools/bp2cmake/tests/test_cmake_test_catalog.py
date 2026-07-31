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
set(ART_JDK_ROOT "{(tmp_path / 'jdk-21').as_posix()}")
set(ART_TARGET_BUNDLE_ROOT "{(tmp_path / 'bundle').as_posix()}")
set(MDVM_COMPAT_INCLUDE_DIR "{(repo / 'compat' / 'include').as_posix()}")
set(MDVM_GENSRC_DIR "{(tmp_path / 'gensrc').as_posix()}")
set(MDVM_NATIVE_SRC_ROOT_DIR "{(repo / 'vendor').as_posix()}")
set(_art_windows_cxx_include "")
set(_art_windows_system_includes "")
set(_art_windows_system_compile_options "")
set(_art_bundle_lib "{(tmp_path / 'bundle' / 'lib').as_posix()}")
add_library(art INTERFACE)
add_executable(dalvikvm IMPORTED GLOBAL)
set_target_properties(dalvikvm PROPERTIES IMPORTED_LOCATION "{tmp_path / 'dalvikvm.exe'}")
foreach(_art_runtime_library IN ITEMS icu_jni javacore openjdk openjdkjvm)
  add_library(${{_art_runtime_library}} SHARED IMPORTED GLOBAL)
endforeach()
add_library(crypto_static INTERFACE)
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
    assert len(catalog["probes"]) == 84
    assert sum(probe["applicable"] for probe in catalog["probes"]) == 82
    assert sum(bool(probe["target_ids"]) for probe in catalog["probes"]) == 22
    assert sum(not probe["target_ids"] for probe in catalog["probes"]) == 62
    assert sum(
        probe["execution"] == "target-runnable" for probe in catalog["probes"]
    ) == 19
    assert {
        probe["name"]: probe["timeout_seconds"]
        for probe in catalog["probes"]
        if probe["timeout_seconds"] is not None
    } == {
        "windows_x64_w013_mem_map_probe": 60,
        "windows_x64_w013_mspace_owner_probe": 60,
        "windows_x64_w013_dlmalloc_config_probe": 60,
        "managed_w013_non_moving_128m": 300,
        "managed_w013_non_moving_1024m": 300,
        "windows_x64_pthread_once_probe": 180,
        "win32_thread_stack_probe": 240,
        "win32_stack_page_probe": 240,
        "win32_stack_growth_probe": 900,
        "win32_stack_growth_rx_probe": 120,
        "win32_cet_policy_probe": 120,
    }
    assert [
        probe["name"] for probe in catalog["probes"] if probe["ctest_registered"]
    ] == ["windows_w013_source_policy"]


def test_linux_catalog_registers_runtime_and_dso_command_gates(tmp_path):
    cmake = shutil.which("cmake")
    if cmake is None:
        pytest.skip("CMake is unavailable")

    repo = Path(__file__).resolve().parents[3]
    source = tmp_path / "source"
    binary = tmp_path / "build"
    source.mkdir()
    profile = source / "target_profile.cmake"
    profile.write_text(
        resolve_target("linux-x86_64-gnu").to_cmake(), encoding="utf-8"
    )
    cmake_lists = f"""
cmake_minimum_required(VERSION 3.16)
project(ArtLinuxTestCatalogFixture C CXX ASM)
include("{profile.as_posix()}")
set(ART_ENABLE_TARGET_RUNTIME_TESTS ON)
set(ART_JDK_ROOT "{(tmp_path / 'jdk-21').as_posix()}")
add_executable(dalvikvm IMPORTED GLOBAL)
set_target_properties(dalvikvm PROPERTIES IMPORTED_LOCATION "{tmp_path / 'dalvikvm'}")
foreach(_art_runtime_library IN ITEMS icu_jni javacore openjdk)
  add_library(${{_art_runtime_library}} SHARED IMPORTED GLOBAL)
endforeach()
add_library(art SHARED IMPORTED GLOBAL)
set_target_properties(art PROPERTIES IMPORTED_LOCATION "{tmp_path / 'libart.so'}")
add_library(art-compiler SHARED IMPORTED GLOBAL)
set_target_properties(art-compiler PROPERTIES
    IMPORTED_LOCATION "{tmp_path / 'libart-compiler.so'}")
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
    applicable = [probe for probe in catalog["probes"] if probe["applicable"]]
    assert len(catalog["probes"]) == 84
    assert [probe["name"] for probe in applicable] == [
        "managed_imageless_hello",
        "managed_gc_stress",
        "managed_math_critical",
        "art_runtime_show_version",
        "art_compiler_dso_topology",
        "managed_w013_non_moving",
        "managed_w013_non_moving_128m",
    ]
    assert [probe["stage"] for probe in applicable] == [
        "w004",
        "w004",
        "w004",
        "w004",
        "w004",
        "w013",
        "w013",
    ]
    runnable = [
        probe
        for probe in applicable
        if probe["execution"] == "target-runnable"
    ]
    assert len(runnable) == 6
    assert all(probe["ctest_registered"] for probe in runnable)
    artifact = applicable[-2]
    assert artifact["type"] == "MANAGED"
    assert artifact["execution"] == "compile-only"
    assert not artifact["ctest_registered"]
    gate = applicable[-1]
    assert gate["type"] == "GATE"
    assert gate["target_ids"] == [
        "linux-x86_64-gnu",
        "windows-x86_64-msvc",
    ]
