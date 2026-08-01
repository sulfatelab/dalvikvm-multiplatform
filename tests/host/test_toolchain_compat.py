from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_linux_openjdkjvmti_toolchain_drift_is_module_scoped():
    cmake = (
        REPO_ROOT / "native" / "cmake" / "ArtCompatibility.cmake"
    ).read_text(encoding="utf-8")
    prelude = (
        REPO_ROOT / "compat" / "include" / "mdvm_openjdkjvmti_linux_prelude.h"
    ).read_text(encoding="utf-8")

    assert "target_compile_options(openjdkjvmti PRIVATE" in cmake
    assert "mdvm_openjdkjvmti_linux_prelude.h" in cmake
    assert "using std::nullptr_t;" in prelude
    assert "__GLIBC_PREREQ(2, 38)" in prelude
    assert "ART_LIBARTBASE_BASE_STRLCPY_H_" in prelude


def test_windows_platform_prelude_has_reviewed_target_scope():
    cmake = (
        REPO_ROOT / "native" / "cmake" / "ArtCompatibility.cmake"
    ).read_text(encoding="utf-8")
    target_prelude = (
        "target_compile_options(${_t} PRIVATE\n"
        '                "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-include ${_PRELUDE}>")'
    )
    windows_guarded_prelude = (
        'if(ART_TARGET_PLATFORM STREQUAL "windows" AND\n'
        "           NOT _t IN_LIST _art_windows_prelude_free_targets)\n"
        f"            {target_prelude}\n"
        "        endif()"
    )
    prelude_free_targets = (
        "androidio",
        "art-dex2oat",
        "art-disassembler",
        "artpalette",
        "crypto_static",
        "dalvikvm",
        "dex2oat",
        "elffile",
        "expat",
        "fdlibm",
        "icui18n",
        "icu",
        "icu_jni",
        "icuuc",
        "icuuc_stubdata",
        "log",
        "lzma",
        "nativebridge",
        "nativehelper",
        "nativeloader",
        "odrstatslog",
        "openjdkjvm",
        "profile",
        "procinfo",
        "sigchain",
        "unwindstack",
        "windows_x64_posix_stubs",
        "ziparchive",
    )

    assert cmake.count(target_prelude) == 1
    assert windows_guarded_prelude in cmake
    scope = cmake.split("set(_art_windows_prelude_free_targets", 1)[1].split(")", 1)[0]
    assert set(scope.split()) == set(prelude_free_targets)
    for definition in (
        "_CRT_SECURE_NO_WARNINGS",
        "NOMINMAX",
        "WIN32_LEAN_AND_MEAN",
        "NOGDI",
    ):
        assert definition in cmake
    assert "_t IN_LIST _art_windows_prelude_free_targets" in cmake
    assert "get_target_property(_art_dex2oat_sources art-dex2oat SOURCES)" in cmake
    assert 'MATCHES "/external/boringssl/"' in cmake
    assert "_art_dex2oat_compat_source_count EQUAL 20" in cmake


def test_windows_sdk_macro_hygiene_is_header_owned():
    windows = (REPO_ROOT / "compat" / "include" / "windows.h").read_text(
        encoding="utf-8"
    )
    prelude = (
        REPO_ROOT / "compat" / "include" / "mdvm_windows_x64_prelude.h"
    ).read_text(encoding="utf-8")

    assert "#include_next <windows.h>" in windows
    assert "defined(MDVM_WINDOWS_NO_CALLBACK_MACRO)" in windows
    assert "!defined(MDVM_WINDOWS_KEEP_CONST_MACRO)" in windows
    assert "#undef CONST" in windows
    assert "#undef ERROR" in windows
    assert "#undef __reserved" in windows
    assert "#undef CONST" not in prelude
    assert "#undef ERROR" not in prelude
    assert "#undef __reserved" not in prelude


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
    prelude = (
        REPO_ROOT / "compat" / "include" / "mdvm_windows_x64_prelude.h"
    ).read_text(encoding="utf-8")
    stubs = (
        REPO_ROOT / "compat" / "src" / "windows_x64_posix_stubs.c"
    ).read_text(encoding="utf-8")

    assert "#include <sched.h>" in source
    assert "#include <cstdint>" in atomic_pair
    assert "static constexpr uint32_t kAtomicPairMaxSpins" in atomic_pair
    assert "for (uint32_t i = 0;; ++i)" in atomic_pair
    assert "#include_next <stdlib.h>" in stdlib
    assert "int posix_memalign(void** memptr, size_t alignment, size_t size);" in stdlib
    assert "int posix_memalign(void** memptr, size_t alignment, size_t size);" not in prelude
    assert "int posix_memalign(void** memptr, size_t alignment, size_t size)" in stubs


def test_windows_dex2oat_posix_declarations_are_header_owned():
    stdio = (REPO_ROOT / "compat" / "include" / "stdio.h").read_text(
        encoding="utf-8"
    )
    stat = (REPO_ROOT / "compat" / "include" / "sys" / "stat.h").read_text(
        encoding="utf-8"
    )
    prelude = (
        REPO_ROOT / "compat" / "include" / "mdvm_windows_x64_prelude.h"
    ).read_text(encoding="utf-8")
    stubs = (
        REPO_ROOT / "compat" / "src" / "windows_x64_posix_stubs.c"
    ).read_text(encoding="utf-8")

    assert "#include_next <stdio.h>" in stdio
    assert "ssize_t getline(char** lineptr, size_t* capacity, FILE* stream);" in stdio
    assert "int fchmod(int fd, int mode);" in stat
    assert "ssize_t getline(char** lineptr, size_t* capacity, FILE* stream);" not in prelude
    assert "int fchmod(int fd, int mode);" not in prelude
    assert "ssize_t getline(char** lineptr, size_t* capacity, FILE* stream)" in stubs
    assert "int fchmod(int fd, int mode)" in stubs


def test_windows_unwindstack_uses_posix_header_ownership():
    types = (REPO_ROOT / "compat" / "include" / "sys" / "types.h").read_text(
        encoding="utf-8"
    )
    unistd = (REPO_ROOT / "compat" / "include" / "unistd.h").read_text(
        encoding="utf-8"
    )
    prelude = (
        REPO_ROOT / "compat" / "include" / "mdvm_windows_x64_prelude.h"
    ).read_text(encoding="utf-8")
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
    assert "typedef unsigned short mode_t;" not in prelude
    assert "#define lseek64 _lseeki64" not in prelude
    assert "static inline int getpagesize(void)" not in prelude
    assert "long long lseek64(" not in stubs


def test_windows_nativebridge_uses_posix_mode_header_ownership():
    stat = (REPO_ROOT / "compat" / "include" / "sys" / "stat.h").read_text(
        encoding="utf-8"
    )
    prelude = (
        REPO_ROOT / "compat" / "include" / "mdvm_windows_x64_prelude.h"
    ).read_text(encoding="utf-8")

    assert "#define mkdir(path, mode) _mkdir(path)" in stat
    assert "#define S_IRWXG (S_IRGRP|S_IWGRP|S_IXGRP)" in stat
    assert "#define S_IRWXO (S_IROTH|S_IWOTH|S_IXOTH)" in stat
    assert "#define mkdir(path,mode) _mkdir(path)" not in prelude


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


def test_linux_toolchain_drift_headers_are_source_scoped():
    cmake = (
        REPO_ROOT / "native" / "cmake" / "ArtCompatibility.cmake"
    ).read_text(encoding="utf-8")

    reviewed_shims = (
        ("MDVM_NATIVE_SRC_ROOT_DIR", "art/libartbase/base/file_utils.cc", "filesystem"),
        ("MDVM_NATIVE_SRC_ROOT_DIR", "art/libartbase/base/time_utils.cc", "limits"),
        ("MDVM_NATIVE_SRC_ROOT_DIR", "art/runtime/runtime_common.cc", "signal.h"),
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
