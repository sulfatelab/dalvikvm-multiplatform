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


def test_graph_wide_compatibility_prelude_is_windows_only():
    cmake = (
        REPO_ROOT / "native" / "cmake" / "ArtCompatibility.cmake"
    ).read_text(encoding="utf-8")
    target_prelude = (
        "target_compile_options(${_t} PRIVATE\n"
        '                "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-include ${_PRELUDE}>")'
    )
    windows_guarded_prelude = (
        'if(ART_TARGET_PLATFORM STREQUAL "windows")\n'
        f"            {target_prelude}\n"
        "        endif()"
    )

    assert cmake.count(target_prelude) == 1
    assert windows_guarded_prelude in cmake


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
