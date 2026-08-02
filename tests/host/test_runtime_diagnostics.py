from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_common_runtime_bringup_diagnostics_are_target_neutral():
    expected_by_source = {
        "vendor/art/dalvikvm/dalvikvm.cc": "dalvikvm InvokeMain:",
        "vendor/art/runtime/runtime.cc": "ART CreateSystemClassLoader",
        "vendor/art/runtime/native/dalvik_system_VMRuntime.cc": (
            "ART VMRuntime_classPath"
        ),
        "vendor/art/runtime/native/dalvik_system_DexFile.cc": (
            "ART DexFile_openDexFileNative"
        ),
    }
    forbidden = (
        "Windows x64 InvokeMain:",
        "Windows x64 CreateSystemClassLoader",
        "Windows x64 Runtime::Start after CreateSystemClassLoader",
        "Windows x64 Runtime::Start before InitNonZygoteOrPostFork",
        "Windows x64 Runtime::Start after InitNonZygoteOrPostFork",
        "Windows x64 Runtime::Start before StartDaemonThreads",
        "Windows x64 Runtime::Start after StartDaemonThreads",
        "Windows x64 Runtime::Start after kInit phase",
        "Windows x64 Runtime::Start finished_starting_=true",
        "Windows x64 VMRuntime_classPath",
        "Windows x64 DexFile_openDexFileNative",
    )

    combined = ""
    for relative, expected in expected_by_source.items():
        text = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert expected in text
        combined += text
    for stale in forbidden:
        assert stale not in combined
