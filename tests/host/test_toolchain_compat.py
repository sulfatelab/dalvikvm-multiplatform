from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_linux_openjdkjvmti_uses_target_checked_source_scoped_compatibility():
    cmake = (
        REPO_ROOT / "native" / "cmake" / "ArtCompatibility.cmake"
    ).read_text(encoding="utf-8")
    compat = (
        REPO_ROOT / "compat" / "include" / "mdvm_bionic_nullptr_compat.h"
    ).read_text(encoding="utf-8")

    assert 'check_symbol_exists(strlcpy "string.h" ART_TARGET_HAS_STRLCPY)' in cmake
    assert "ART_LIBARTBASE_BASE_STRLCPY_H_" in cmake
    assert 'SHELL:-include string.h' in cmake
    assert "target_compile_options(openjdkjvmti PRIVATE" in cmake
    assert "mdvm_bionic_nullptr_compat.h" in cmake
    assert "using std::nullptr_t;" in compat
    source_scope = cmake.split(
        "set(_art_jvmti_bionic_nullptr_sources", 1
    )[1].split(")", 1)[0]
    reviewed_sources = {
        "deopt_manager.cc",
        "events.cc",
        "object_tagging.cc",
        "OpenjdkJvmTi.cc",
        "ti_breakpoint.cc",
        "ti_class.cc",
        "ti_class_loader.cc",
        "ti_dump.cc",
        "ti_heap.cc",
        "ti_method.cc",
        "ti_phase.cc",
        "ti_redefine.cc",
        "ti_stack.cc",
        "ti_thread.cc",
        "transform.cc",
    }
    assert {line.strip() for line in source_scope.splitlines() if ".cc" in line} == (
        reviewed_sources
    )
    assert not (
        REPO_ROOT / "compat" / "include" / "mdvm_openjdkjvmti_linux_prelude.h"
    ).exists()


def test_windows_product_targets_use_explicit_definitions_without_a_prelude():
    cmake = (
        REPO_ROOT / "native" / "cmake" / "ArtCompatibility.cmake"
    ).read_text(encoding="utf-8")
    test_cmake = (REPO_ROOT / "tests" / "CMakeLists.txt").read_text(encoding="utf-8")
    codegen = (
        REPO_ROOT / "tools" / "bp2cmake" / "bp2cmake" / "codegen.py"
    ).read_text(encoding="utf-8")
    windows_prelude = (
        REPO_ROOT / "compat" / "include" / "mdvm_windows_x64_prelude.h"
    )
    assert "mdvm_windows_x64_prelude.h" not in cmake
    assert "mdvm_windows_x64_prelude.h" not in test_cmake
    assert "mdvm_windows_x64_prelude.h" not in codegen
    assert not windows_prelude.exists()
    assert "_art_windows_prelude_free_targets" not in cmake
    for definition in (
        "_CRT_SECURE_NO_WARNINGS",
        "NOMINMAX",
        "WIN32_LEAN_AND_MEAN",
        "NOGDI",
    ):
        assert definition in cmake
    assert 'if(ART_TARGET_PLATFORM STREQUAL "windows")\n' in cmake
    assert "target_compile_definitions(${_t} PRIVATE" in cmake
    assert "get_target_property(_art_dex2oat_sources art-dex2oat SOURCES)" not in cmake
    assert "libbase/hex.cpp" not in cmake
    for relative in (
        "tests/cases/jit-mapping/probe.cc",
        "tests/cases/jit-section-policy/probe.cc",
    ):
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert source.index("#include <windows.h>") < source.index("#include <psapi.h>")


def test_windows_sdk_macro_hygiene_is_header_owned():
    windows = (REPO_ROOT / "compat" / "include" / "windows.h").read_text(
        encoding="utf-8"
    )
    strings = (REPO_ROOT / "compat" / "include" / "string.h").read_text(
        encoding="utf-8"
    )

    assert "#include_next <windows.h>" in windows
    assert "defined(MDVM_WINDOWS_NO_CALLBACK_MACRO)" in windows
    assert "!defined(MDVM_WINDOWS_KEEP_CONST_MACRO)" in windows
    assert "#undef CONST" in windows
    assert "#undef ERROR" in windows
    assert "#undef __reserved" in windows
    assert "#undef ZeroMemory" not in windows
    assert "#define strcasecmp _stricmp" in strings
    assert "#define strncasecmp _strnicmp" in strings


def test_windows_artbase_uses_project_mman_and_sdk_macro_hygiene():
    mman = (
        REPO_ROOT / "vendor" / "art" / "libartbase" / "base" / "mman.h"
    ).read_text(encoding="utf-8")
    mem_map = (
        REPO_ROOT / "vendor" / "art" / "libartbase" / "base" / "mem_map.cc"
    ).read_text(encoding="utf-8")
    time_utils = (
        REPO_ROOT / "vendor" / "art" / "libartbase" / "base" / "time_utils.cc"
    ).read_text(encoding="utf-8")

    assert "#include <sys/mman.h>" in mman
    assert "There is no sys/mman.h in mingw" not in mman
    assert "MDVM_UNDEFINE_ZEROMEMORY" not in mem_map
    assert "#ifdef ZeroMemory\n#undef ZeroMemory\n#endif" in mem_map
    assert mem_map.rfind("#undef ZeroMemory") > mem_map.rfind('#include "utils.h"')
    assert "#include <sys/time.h>" in time_utils
    assert "#if defined(__APPLE__)\n#include <sys/time.h>" not in time_utils


def test_windows_dex2oat_compatibility_is_header_and_source_scoped():
    cmake = (
        REPO_ROOT / "native" / "cmake" / "ArtCompatibility.cmake"
    ).read_text(encoding="utf-8")
    malloc = (REPO_ROOT / "compat" / "include" / "malloc.h").read_text(
        encoding="utf-8"
    )
    oat_writer = (
        REPO_ROOT / "compat" / "include" / "mdvm_windows_oat_writer_compat.h"
    ).read_text(encoding="utf-8")
    assert "struct mallinfo" in malloc
    assert "MDVM_WINDOWS_DEX2OAT_COMPAT" in malloc
    assert "class OatWriter;" in oat_writer
    assert cmake.count("mdvm_windows_oat_writer_compat.h") == 1
    assert "art/dex2oat/linker/oat_writer.cc" in cmake


def test_windows_openjdkjvm_uses_explicit_source_and_header_contracts():
    source = (REPO_ROOT / "vendor" / "art" / "openjdkjvm" / "OpenjdkJvm.cc").read_text(
        encoding="utf-8"
    )
    atomic_pair = (
        REPO_ROOT / "vendor" / "art" / "runtime" / "base" / "atomic_pair.h"
    ).read_text(encoding="utf-8")
    stdlib = (REPO_ROOT / "compat" / "include" / "stdlib.h").read_text(
        encoding="utf-8"
    )
    stubs = (
        REPO_ROOT / "compat" / "src" / "windows_x64_posix_stubs.c"
    ).read_text(encoding="utf-8")

    assert "#include <sched.h>" in source
    assert "#include <cstdint>" in atomic_pair
    assert "static constexpr uint32_t kAtomicPairMaxSpins" in atomic_pair
    assert "for (uint32_t i = 0;; ++i)" in atomic_pair
    assert "#include_next <stdlib.h>" in stdlib
    assert "int posix_memalign(void** memptr, size_t alignment, size_t size);" in stdlib
    assert "int posix_memalign(void** memptr, size_t alignment, size_t size)" in stubs


def test_windows_art_compiler_owns_rand_r_contract():
    scheduler = (
        REPO_ROOT / "vendor" / "art" / "compiler" / "optimizing" / "scheduler.h"
    ).read_text(encoding="utf-8")
    stdlib = (REPO_ROOT / "compat" / "include" / "stdlib.h").read_text(
        encoding="utf-8"
    )
    assert "#include <stdlib.h>" in scheduler
    assert "static inline int rand_r(unsigned int* seed)" in stdlib


def test_windows_art_runtime_owns_platform_contracts():
    art = REPO_ROOT / "vendor" / "art"
    sched_consumers = (
        "runtime/base/locks.cc",
        "runtime/base/mutex.cc",
        "runtime/class_linker.cc",
        "runtime/gc/collector/mark_compact.cc",
        "runtime/jit/jit_memory_region_test.cc",
        "runtime/monitor.cc",
        "runtime/native/java_lang_Thread.cc",
        "runtime/native_bridge_art_interface.cc",
        "runtime/thread.cc",
        "runtime/thread_list.cc",
    )
    for relative in sched_consumers:
        source = (art / relative).read_text(encoding="utf-8")
        assert "sched_yield" in source or "CLONE_NEWNS" in source
        assert "#include <sched.h>" in source

    mutex = (art / "runtime" / "base" / "mutex.cc").read_text(encoding="utf-8")
    region = (art / "runtime" / "gc" / "space" / "region_space.cc").read_text(
        encoding="utf-8"
    )
    mark_compact = (
        art / "runtime" / "gc" / "collector" / "mark_compact.cc"
    ).read_text(encoding="utf-8")
    runtime_common = (art / "runtime" / "runtime_common.h").read_text(
        encoding="utf-8"
    )
    types = (REPO_ROOT / "compat" / "include" / "sys" / "types.h").read_text(
        encoding="utf-8"
    )
    assert "std::atomic<uint>" not in mutex
    assert "static constexpr uint " not in region
    assert "static_cast<uint>(state_)" not in region
    assert "static constexpr uint " not in mark_compact
    assert "#include <signal.h>" in runtime_common
    assert "typedef int id_t;" in types


def test_windows_openjdkjvmti_owns_sched_yield_declaration():
    deopt_manager = (
        REPO_ROOT / "vendor" / "art" / "openjdkjvmti" / "deopt_manager.cc"
    ).read_text(encoding="utf-8")

    assert "#include <sched.h>" in deopt_manager
    assert "sched_yield();" in deopt_manager


def test_windows_dex2oat_posix_declarations_are_header_owned():
    stdio = (REPO_ROOT / "compat" / "include" / "stdio.h").read_text(
        encoding="utf-8"
    )
    stat = (REPO_ROOT / "compat" / "include" / "sys" / "stat.h").read_text(
        encoding="utf-8"
    )
    stubs = (
        REPO_ROOT / "compat" / "src" / "windows_x64_posix_stubs.c"
    ).read_text(encoding="utf-8")

    assert "#include_next <stdio.h>" in stdio
    assert "ssize_t getline(char** lineptr, size_t* capacity, FILE* stream);" in stdio
    assert "int fchmod(int fd, int mode);" in stat
    assert "ssize_t getline(char** lineptr, size_t* capacity, FILE* stream)" in stubs
    assert "int fchmod(int fd, int mode)" in stubs


def test_windows_unwindstack_uses_posix_header_ownership():
    types = (REPO_ROOT / "compat" / "include" / "sys" / "types.h").read_text(
        encoding="utf-8"
    )
    unistd = (REPO_ROOT / "compat" / "include" / "unistd.h").read_text(
        encoding="utf-8"
    )
    stubs = (
        REPO_ROOT / "compat" / "src" / "windows_x64_posix_stubs.c"
    ).read_text(encoding="utf-8")

    assert "#include_next <sys/types.h>" in types
    assert "typedef unsigned short mode_t;" in types
    assert "typedef int pid_t;" in types
    assert "typedef intptr_t ssize_t;" in types
    assert "static inline int getpagesize(void)" in unistd
    assert "sysconf(_SC_PAGESIZE)" in unistd
    assert "#define lseek64 _lseeki64" in unistd
    assert "long long lseek64(" not in stubs


def test_windows_nativebridge_uses_posix_mode_header_ownership():
    stat = (REPO_ROOT / "compat" / "include" / "sys" / "stat.h").read_text(
        encoding="utf-8"
    )
    assert "#define mkdir(path, mode) _mkdir(path)" in stat
    assert "#define S_IRWXG (S_IRGRP|S_IWGRP|S_IXGRP)" in stat
    assert "#define S_IRWXO (S_IROTH|S_IWOTH|S_IXOTH)" in stat


def test_windows_ziparchive_owns_64_bit_stdio_spellings():
    cmake = (
        REPO_ROOT / "native" / "cmake" / "ArtCompatibility.cmake"
    ).read_text(encoding="utf-8")

    scope = cmake.split("target_compile_definitions(ziparchive PRIVATE", 1)[1].split(
        ")", 1
    )[0]
    for definition in (
        "fseeko=_fseeki64",
        "fseeko64=_fseeki64",
        "ftello=_ftelli64",
        "ftello64=_ftelli64",
    ):
        assert definition in scope


def test_linux_toolchain_drift_is_explicit_and_source_scoped():
    cmake = (
        REPO_ROOT / "native" / "cmake" / "ArtCompatibility.cmake"
    ).read_text(encoding="utf-8")

    reviewed_shims = (
        ("MDVM_NATIVE_SRC_ROOT_DIR", "art/libartbase/base/file_utils.cc", "filesystem"),
        ("MDVM_NATIVE_SRC_ROOT_DIR", "art/libartbase/base/time_utils.cc", "limits"),
        ("MDVM_GENSRC_DIR", "art/libdexfile/dex/invoke_type.h.operator_out.cc", "stdint.h"),
    )
    linux_blocks = cmake.split('if(ART_TARGET_PLATFORM STREQUAL "linux")')[1:]
    for root, source, header in reviewed_shims:
        block = (
            "set_property(SOURCE\n"
            f"        ${{{root}}}/{source}\n"
            f'        APPEND PROPERTY COMPILE_OPTIONS "-include;{header}")'
        )
        assert any(block in guarded.split("endif()", 1)[0] for guarded in linux_blocks)

    assert "mdvm_toolchain_prelude.h" not in cmake
    assert "${_PRELUDE}" not in cmake
    assert not (
        REPO_ROOT / "compat" / "include" / "mdvm_toolchain_prelude.h"
    ).exists()
    assert "libprocinfo/process.cpp" not in cmake
    assert "art/libartbase/base/metrics/metrics_common.cc" not in cmake


def test_product_graph_has_no_tree_wide_warning_as_error_demotion():
    cmake = (
        REPO_ROOT / "native" / "cmake" / "ArtCompatibility.cmake"
    ).read_text(encoding="utf-8")

    assert "-Wno-error" not in cmake


def test_template_shadow_demotion_is_source_scoped():
    cmake = (
        REPO_ROOT / "native" / "cmake" / "ArtCompatibility.cmake"
    ).read_text(encoding="utf-8")

    assert "-Wno-strict-primary-template-shadow" in cmake
    assert (
        '"$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-strict-primary-template-shadow>"'
        not in cmake
    )
