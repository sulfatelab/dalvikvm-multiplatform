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
set(ART_LLVM_READOBJ "{(tmp_path / 'llvm-readobj').as_posix()}")
set(ART_LLVM_OBJDUMP "{(tmp_path / 'llvm-objdump').as_posix()}")
set(ART_TARGET_BUNDLE_ROOT "{(tmp_path / 'bundle').as_posix()}")
set(MDVM_COMPAT_INCLUDE_DIR "{(repo / 'compat' / 'include').as_posix()}")
set(MDVM_GENSRC_DIR "{(tmp_path / 'gensrc').as_posix()}")
set(MDVM_NATIVE_SRC_ROOT_DIR "{(repo / 'vendor').as_posix()}")
set(_art_windows_cxx_include "")
set(_art_windows_system_includes "")
set(_art_windows_system_compile_options "")
set(_art_bundle_lib "{(tmp_path / 'bundle' / 'lib').as_posix()}")
add_library(art SHARED IMPORTED GLOBAL)
set_target_properties(art PROPERTIES IMPORTED_LOCATION "{tmp_path / 'art.dll'}")
add_executable(dalvikvm IMPORTED GLOBAL)
set_target_properties(dalvikvm PROPERTIES IMPORTED_LOCATION "{tmp_path / 'dalvikvm.exe'}")
foreach(_art_runtime_library IN ITEMS icu_jni javacore openjdk openjdkjvm)
  add_library(${{_art_runtime_library}} SHARED IMPORTED GLOBAL)
endforeach()
add_library(openjdkjvmti SHARED IMPORTED GLOBAL)
set_target_properties(openjdkjvmti PROPERTIES IMPORTED_LOCATION "{tmp_path / 'openjdkjvmti.dll'}")
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
    assert len(catalog["probes"]) == 89
    assert sum(probe["applicable"] for probe in catalog["probes"]) == 87
    assert sum(bool(probe["target_ids"]) for probe in catalog["probes"]) == 25
    assert sum(not probe["target_ids"] for probe in catalog["probes"]) == 64
    w002_attach = next(
        probe for probe in catalog["probes"] if probe["name"] == "managed_w002_attach"
    )
    w002_osr = next(
        probe for probe in catalog["probes"] if probe["name"] == "managed_w002_osr"
    )
    w002_structure = next(
        probe
        for probe in catalog["probes"]
        if probe["name"] == "windows_w002_managed_entry_structure"
    )
    assert w002_attach["execution"] == "target-runnable"
    assert w002_osr["execution"] == "target-runnable"
    assert w002_attach["timeout_seconds"] == 600
    assert w002_osr["timeout_seconds"] == 600
    assert w002_attach["ctest_registered"] is False
    assert w002_osr["ctest_registered"] is False
    assert w002_structure["execution"] == "host-review"
    assert w002_structure["ctest_registered"] is True
    w003_structure = next(
        probe
        for probe in catalog["probes"]
        if probe["name"] == "windows_w003_quick_boundary_structure"
    )
    assert w003_structure["execution"] == "host-review"
    assert w003_structure["ctest_registered"] is True
    assert sum(
        probe["execution"] == "target-runnable" for probe in catalog["probes"]
    ) == 53
    assert {
        probe["name"]: probe["timeout_seconds"]
        for probe in catalog["probes"]
        if probe["timeout_seconds"] is not None
    } == {
        "managed_w002_attach": 600,
        "managed_w002_osr": 600,
        "managed_critical_native": 1200,
        "managed_native_abi": 900,
        "managed_w003_xmm_sentinel": 1200,
        "managed_jvmti_force": 1200,
        "managed_coreprobe": 600,
        "managed_dnsprobe": 600,
        "managed_gcforced": 600,
        "managed_gcprobe": 600,
        "managed_goldenapp": 600,
        "managed_interruptprobe": 600,
        "managed_ioprobe": 600,
        "managed_netprobe": 600,
        "managed_oserrnoprobe": 600,
        "managed_propsprobe": 600,
        "managed_rtmem": 600,
        "managed_threadstressprobe": 600,
        "managed_throwprobe": 600,
        "win32_uef_probe": 600,
        "win32_fault_record_probe": 60,
        "win32_sigchain_probe": 60,
        "win32_debugger_probe": 600,
        "managed_crashabortprobe": 300,
        "managed_crashnativeprobe": 900,
        "managed_w010_fault_recovery": 1200,
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
        "win32_stack_pregrow_probe": 1200,
        "win32_cet_policy_probe": 120,
        "win32_jit_unwind_info_probe": 120,
        "win32_jit_unwind_registry_probe": 120,
        "managed_jit_unwind_lifecycle": 600,
        "managed_w025_jit_lifecycle_stress": 1200,
        "managed_w025_jit_mapping": 1200,
        "windows_x64_w025_section_policy_probe": 900,
        "windows_x64_w025_policy_launcher": 1200,
    }
    assert [
        probe["name"] for probe in catalog["probes"] if probe["ctest_registered"]
    ] == [
        "windows_w002_managed_entry_structure",
        "windows_w003_quick_boundary_structure",
        "windows_w004_runtime_load_structure",
        "windows_w013_source_policy",
        "windows_x64_w025_jit_structure",
    ]
    w025 = [probe for probe in catalog["probes"] if probe["stage"] == "w025"]
    assert len(w025) == 11
    assert sum(probe["execution"] == "target-runnable" for probe in w025) == 7
    assert sum(probe["execution"] == "host-review" for probe in w025) == 1
    assert sum(probe["execution"] == "compile-only" for probe in w025) == 3
    assert [probe["name"] for probe in w025 if probe["ctest_registered"]] == [
        "windows_x64_w025_jit_structure",
    ]

    variant_binary = tmp_path / "variant-build"
    (source / "CMakeLists.txt").write_text(
        cmake_lists.replace(
            "set(ART_ENABLE_TARGET_RUNTIME_TESTS OFF)",
            "set(ART_ENABLE_TARGET_RUNTIME_TESTS ON)\n"
            "set(ART_TEST_VARIANT win32-stack-high-water)",
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [cmake, "-S", str(source), "-B", str(variant_binary), "-G", "Ninja"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    variant_catalog = json.loads(
        (variant_binary / "art-tests" / "art_test_catalog.json").read_text(
            encoding="utf-8"
        )
    )
    fs1 = next(
        probe
        for probe in variant_catalog["probes"]
        if probe["name"] == "managed_fs1_stack_high_water"
    )
    assert fs1["execution"] == "target-runnable"
    assert fs1["timeout_seconds"] == 900
    assert fs1["ctest_registered"] is True
    fs1_structure = next(
        probe
        for probe in variant_catalog["probes"]
        if probe["name"] == "win32_fs1_stack_high_water_structure"
    )
    assert fs1_structure["execution"] == "host-review"
    assert fs1_structure["ctest_registered"] is True

    frame_binary = tmp_path / "frame-variant-build"
    (source / "CMakeLists.txt").write_text(
        cmake_lists.replace(
            "set(ART_ENABLE_TARGET_RUNTIME_TESTS OFF)",
            "set(ART_ENABLE_TARGET_RUNTIME_TESTS ON)\n"
            "set(ART_TEST_VARIANT win32-frame-attribution)",
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [cmake, "-S", str(source), "-B", str(frame_binary), "-G", "Ninja"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    frame_catalog = json.loads(
        (frame_binary / "art-tests" / "art_test_catalog.json").read_text(
            encoding="utf-8"
        )
    )
    frame = next(
        probe
        for probe in frame_catalog["probes"]
        if probe["name"] == "managed_w003_frame"
    )
    assert frame["execution"] == "target-runnable"
    assert frame["timeout_seconds"] == 1800
    assert frame["ctest_registered"] is True


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
set(ART_LLVM_READOBJ "{(tmp_path / 'llvm-readobj').as_posix()}")
set(ART_LLVM_OBJDUMP "{(tmp_path / 'llvm-objdump').as_posix()}")
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
    assert len(catalog["probes"]) == 89
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
