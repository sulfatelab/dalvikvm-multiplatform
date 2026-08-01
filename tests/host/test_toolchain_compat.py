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


def test_product_graph_has_no_tree_wide_warning_as_error_demotion():
    cmake = (
        REPO_ROOT / "native" / "cmake" / "ArtCompatibility.cmake"
    ).read_text(encoding="utf-8")

    assert "-Wno-error" not in cmake
