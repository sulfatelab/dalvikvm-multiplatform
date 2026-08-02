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
set(ART_LLVM_PDBUTIL "{(tmp_path / 'llvm-pdbutil').as_posix()}")
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
foreach(_art_runtime_library IN ITEMS icu_jni javacore javacrypto openjdk openjdkjvm)
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
    assert len(catalog["probes"]) == 93
    assert sum(probe["applicable"] for probe in catalog["probes"]) == 90
    assert sum(bool(probe["target_ids"]) for probe in catalog["probes"]) == 35
    assert sum(not probe["target_ids"] for probe in catalog["probes"]) == 58
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
    for name in (
        "criticalnativeprobe",
        "nativeabiprobe",
        "managed_critical_native",
        "managed_native_abi",
        "managed_perfsmokeprobe",
        "managed_threadheavyprobe",
    ):
        probe = next(probe for probe in catalog["probes"] if probe["name"] == name)
        assert probe["target_ids"] == [
            "linux-x86_64-gnu",
            "linux-aarch64-gnu",
            "windows-x86_64-msvc",
        ]
    embedding = next(
        probe
        for probe in catalog["probes"]
        if probe["name"] == "win32_art_embedding_probe"
    )
    assert embedding["target_ids"] == ["windows-x86_64-msvc"]
    assert embedding["execution"] == "target-runnable"
    assert embedding["timeout_seconds"] == 600
    assert embedding["ctest_registered"] is False
    udp = next(
        probe for probe in catalog["probes"] if probe["name"] == "managed_udpprobe"
    )
    assert udp["platforms"] == ["windows"]
    assert udp["target_arches"] == ["x86_64"]
    assert udp["target_abis"] == ["msvc"]
    assert udp["execution"] == "target-runnable"
    assert udp["timeout_seconds"] == 600
    assert udp["ctest_registered"] is False
    locale = next(
        probe
        for probe in catalog["probes"]
        if probe["name"] == "managed_localeprobe"
    )
    assert locale["platforms"] == ["windows"]
    assert locale["target_arches"] == ["x86_64"]
    assert locale["target_abis"] == ["msvc"]
    assert locale["execution"] == "target-runnable"
    assert locale["timeout_seconds"] == 600
    assert locale["ctest_registered"] is False
    zip_probe = next(
        probe
        for probe in catalog["probes"]
        if probe["name"] == "managed_zipprobe"
    )
    assert zip_probe["platforms"] == ["windows"]
    assert zip_probe["target_arches"] == ["x86_64"]
    assert zip_probe["target_abis"] == ["msvc"]
    assert zip_probe["execution"] == "target-runnable"
    assert zip_probe["timeout_seconds"] == 600
    assert zip_probe["ctest_registered"] is False
    bn = next(
        probe for probe in catalog["probes"] if probe["name"] == "managed_bnprobe"
    )
    assert bn["platforms"] == ["windows"]
    assert bn["target_arches"] == ["x86_64"]
    assert bn["target_abis"] == ["msvc"]
    assert bn["execution"] == "target-runnable"
    assert bn["timeout_seconds"] == 600
    assert bn["ctest_registered"] is False
    os_constants = next(
        probe
        for probe in catalog["probes"]
        if probe["name"] == "managed_osconstantsprobe"
    )
    assert os_constants["platforms"] == ["windows"]
    assert os_constants["target_arches"] == ["x86_64"]
    assert os_constants["target_abis"] == ["msvc"]
    assert os_constants["execution"] == "target-runnable"
    assert os_constants["timeout_seconds"] == 600
    assert os_constants["ctest_registered"] is False
    xml = next(
        probe for probe in catalog["probes"] if probe["name"] == "managed_xmlprobe"
    )
    assert xml["platforms"] == ["windows"]
    assert xml["target_arches"] == ["x86_64"]
    assert xml["target_abis"] == ["msvc"]
    assert xml["execution"] == "target-runnable"
    assert xml["timeout_seconds"] == 600
    assert xml["ctest_registered"] is False
    socket_address = next(
        probe
        for probe in catalog["probes"]
        if probe["name"] == "managed_socketaddressprobe"
    )
    assert socket_address["platforms"] == ["windows"]
    assert socket_address["target_arches"] == ["x86_64"]
    assert socket_address["target_abis"] == ["msvc"]
    assert socket_address["execution"] == "target-runnable"
    assert socket_address["timeout_seconds"] == 600
    assert socket_address["ctest_registered"] is False
    async_close = next(
        probe
        for probe in catalog["probes"]
        if probe["name"] == "managed_asynccloseprobe"
    )
    assert async_close["platforms"] == ["windows"]
    assert async_close["target_arches"] == ["x86_64"]
    assert async_close["target_abis"] == ["msvc"]
    assert async_close["execution"] == "target-runnable"
    assert async_close["timeout_seconds"] == 600
    assert async_close["ctest_registered"] is False
    assert sum(
        probe["execution"] == "target-runnable" for probe in catalog["probes"]
    ) == 72
    assert all(
        probe["type"] != "SHARED"
        for probe in catalog["probes"]
        if probe["execution"] == "target-runnable"
    )
    assert all(
        probe["type"] != "GATE"
        for probe in catalog["probes"]
        if probe["execution"] == "compile-only"
    )
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
        "managed_boot_image_hello": 180,
        "win32_art_embedding_probe": 600,
        "managed_jvmti_force": 1200,
        "managed_pathprobe": 600,
        "managed_abspathprobe": 600,
        "managed_asynccloseprobe": 600,
        "managed_bnprobe": 600,
        "managed_coreprobe": 600,
        "managed_dnsprobe": 600,
        "managed_gcforced": 600,
        "managed_gcprobe": 600,
        "managed_goldenapp": 600,
        "managed_handleleakprobe": 600,
        "managed_interruptprobe": 600,
        "managed_ioprobe": 600,
        "managed_execprobe": 600,
        "managed_ipv6probe": 600,
        "managed_localeprobe": 600,
        "managed_netprobe": 600,
        "managed_osconstantsprobe": 600,
        "managed_oserrnoprobe": 600,
        "managed_perfsmokeprobe": 600,
        "managed_propsprobe": 600,
        "managed_rtmem": 600,
        "managed_socketaddressprobe": 600,
        "managed_sslproviderprobe": 600,
        "managed_threadheavyprobe": 600,
        "managed_threadstressprobe": 600,
        "managed_throwprobe": 600,
        "managed_udpprobe": 600,
        "managed_xmlprobe": 600,
        "managed_zipprobe": 600,
        "win32_uef_probe": 600,
        "win32_fault_record_probe": 60,
        "win32_sigchain_probe": 60,
        "win32_debugger_probe": 600,
        "managed_crashabortprobe": 300,
        "managed_crashnativeprobe": 900,
        "managed_w010_fault_recovery": 1200,
        "windows_w013_mem_map_probe": 60,
        "windows_w013_mspace_owner_probe": 60,
        "windows_w013_dlmalloc_config_probe": 60,
        "managed_w013_non_moving_128m": 300,
        "managed_w013_non_moving_1024m": 300,
        "windows_w014_pthread_once_probe": 180,
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
        "windows_w025_section_policy_probe": 900,
        "windows_w025_policy_launcher": 1200,
        "windows_w025_jit_runtime_controls": 1800,
    }
    assert [
        probe["name"] for probe in catalog["probes"] if probe["ctest_registered"]
    ] == [
        "windows_w002_managed_entry_structure",
        "windows_w003_quick_boundary_structure",
        "windows_w004_runtime_load_structure",
        "windows_w010_boundary_unwind_structure",
        "windows_w013_source_policy",
        "win32_fs1_stack_high_water_structure",
        "windows_w025_jit_structure",
        "windows_w027_unicode_api_policy",
    ]
    w025 = [probe for probe in catalog["probes"] if probe["stage"] == "w025"]
    assert len(w025) == 12
    assert sum(probe["execution"] == "target-runnable" for probe in w025) == 8
    assert sum(probe["execution"] == "host-review" for probe in w025) == 1
    assert sum(probe["execution"] == "compile-only" for probe in w025) == 3
    assert [probe["name"] for probe in w025 if probe["ctest_registered"]] == [
        "windows_w025_jit_structure",
    ]
    w027 = [probe for probe in catalog["probes"] if probe["stage"] == "w027"]
    assert len(w027) == 1
    assert w027[0]["name"] == "windows_w027_unicode_api_policy"
    assert w027[0]["execution"] == "host-review"
    assert w027[0]["ctest_registered"] is True
    assert w027[0]["platforms"] == ["windows"]
    assert w027[0]["target_arches"] == ["x86_64"]
    assert w027[0]["target_abis"] == ["msvc"]

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


def test_linux_catalog_registers_evidenced_runtime_slice(tmp_path):
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
add_executable(dex2oat IMPORTED GLOBAL)
set_target_properties(dex2oat PROPERTIES IMPORTED_LOCATION "{tmp_path / 'dex2oat'}")
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
    assert len(catalog["probes"]) == 93
    assert [probe["name"] for probe in applicable] == [
        "criticalnativeprobe",
        "nativeabiprobe",
        "managed_critical_native",
        "managed_native_abi",
        "managed_imageless_hello",
        "managed_boot_image_hello",
        "managed_gc_stress",
        "managed_perfsmokeprobe",
        "managed_threadheavyprobe",
        "managed_math_critical",
        "art_runtime_show_version",
        "art_compiler_dso_topology",
        "managed_w013_non_moving",
        "managed_w013_non_moving_128m",
    ]
    assert [probe["stage"] for probe in applicable] == [
        "w003",
        "w003",
        "w003",
        "w003",
        "w004",
        "w004",
        "w004",
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
    assert len(runnable) == 11
    assert all(probe["ctest_registered"] for probe in runnable)
    artifact = applicable[-2]
    assert artifact["type"] == "MANAGED"
    assert artifact["execution"] == "compile-only"
    assert not artifact["ctest_registered"]
    gate = applicable[-1]
    assert gate["type"] == "GATE"
    assert gate["target_ids"] == [
        "linux-x86_64-gnu",
        "linux-aarch64-gnu",
        "windows-x86_64-msvc",
    ]


def test_linux_aarch64_catalog_registers_only_evidenced_runner_slice(tmp_path):
    cmake = shutil.which("cmake")
    if cmake is None:
        pytest.skip("CMake is unavailable")

    repo = Path(__file__).resolve().parents[3]
    source = tmp_path / "source"
    binary = tmp_path / "build"
    source.mkdir()
    profile = source / "target_profile.cmake"
    profile.write_text(
        resolve_target("linux-aarch64-gnu").to_cmake(), encoding="utf-8"
    )
    cmake_lists = f"""
cmake_minimum_required(VERSION 3.16)
project(ArtLinuxAarch64TestCatalogFixture C CXX ASM)
include("{profile.as_posix()}")
set(ART_ENABLE_TARGET_RUNTIME_TESTS ON)
set(ART_TARGET_RUNNER "{(tmp_path / 'qemu-aarch64').as_posix()}")
set(ART_TARGET_RUNNER_ROOT "{(tmp_path / 'sysroot').as_posix()}")
set(ART_JDK_ROOT "{(tmp_path / 'jdk-21').as_posix()}")
set(ART_LLVM_READOBJ "{(tmp_path / 'llvm-readobj').as_posix()}")
set(ART_LLVM_OBJDUMP "{(tmp_path / 'llvm-objdump').as_posix()}")
add_executable(dalvikvm IMPORTED GLOBAL)
set_target_properties(dalvikvm PROPERTIES IMPORTED_LOCATION "{tmp_path / 'dalvikvm'}")
add_executable(dex2oat IMPORTED GLOBAL)
set_target_properties(dex2oat PROPERTIES IMPORTED_LOCATION "{tmp_path / 'dex2oat'}")
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
        (binary / "art-tests" / "art_test_catalog.json").read_text(
            encoding="utf-8"
        )
    )
    applicable = [probe for probe in catalog["probes"] if probe["applicable"]]
    assert [probe["name"] for probe in applicable] == [
        "criticalnativeprobe",
        "nativeabiprobe",
        "managed_critical_native",
        "managed_native_abi",
        "managed_imageless_hello",
        "managed_gc_stress",
        "managed_perfsmokeprobe",
        "managed_threadheavyprobe",
        "managed_math_critical",
        "art_runtime_show_version",
        "art_compiler_dso_topology",
        "managed_w013_non_moving",
        "managed_w013_non_moving_128m",
    ]
    assert [probe["execution"] for probe in applicable] == [
        "compile-only",
        "compile-only",
        "target-runnable",
        "target-runnable",
        "target-runnable",
        "target-runnable",
        "target-runnable",
        "target-runnable",
        "target-runnable",
        "target-runnable",
        "target-runnable",
        "compile-only",
        "target-runnable",
    ]
    assert [probe["ctest_registered"] for probe in applicable] == [
        False,
        False,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        True,
        False,
        True,
    ]
    ctest = (binary / "art-tests" / "CTestTestfile.cmake").read_text(
        encoding="utf-8"
    )
    assert "--runner" in ctest
    assert "qemu-aarch64" in ctest
    assert "--runner-arg=-L" in ctest
    assert "ART version 2.1.0 arm64" in ctest
    for test_name in (
        "art.w003.managed_critical_native",
        "art.w003.managed_native_abi",
        "art.w004.managed_perfsmokeprobe",
        "art.w004.managed_threadheavyprobe",
        "art.w004.managed_math_critical",
        "art.w004.art_compiler_dso_topology",
    ):
        runner_line = next(
            line
            for line in ctest.splitlines()
            if line.startswith("add_test(") and test_name in line
        )
        assert "--runner" in runner_line
        assert "--runner-arg=-L" in runner_line
    w013_line = next(
        line
        for line in ctest.splitlines()
        if line.startswith("add_test(")
        and "art.w013.managed_w013_non_moving_128m" in line
    )
    assert "--runner" in w013_line
    assert "--runner-arg=-L" in w013_line
