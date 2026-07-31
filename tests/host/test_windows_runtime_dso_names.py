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
    assert "MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS" in stubs
    assert "LoadLibraryW(wide_filename)" in stubs
    assert "LoadLibraryA(" not in stubs
