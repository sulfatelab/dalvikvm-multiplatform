from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_windows_bootstrap_dso_names_match_generated_artifacts():
    runtime = (REPO_ROOT / "vendor" / "art" / "runtime" / "runtime.cc").read_text(
        encoding="utf-8"
    )
    for artifact in ("icu_jni.dll", "javacore.dll", "openjdk.dll"):
        assert f'"{artifact}"' in runtime
        assert f'"lib{artifact}"' not in runtime


def test_windows_dlopen_converts_utf8_and_uses_wide_api():
    stubs = (
        REPO_ROOT / "compat" / "src" / "windows_x64_posix_stubs.c"
    ).read_text(encoding="utf-8")
    utf8_helper = (
        REPO_ROOT / "compat" / "include" / "mdvm_windows_utf8.h"
    ).read_text(encoding="utf-8")
    assert "mdvm_utf8_to_utf16_alloc(filename)" in stubs
    assert "CP_UTF8, MB_ERR_INVALID_CHARS" in utf8_helper
    assert "LoadLibraryW(wide_filename)" in stubs
    assert "LoadLibraryA(" not in stubs
