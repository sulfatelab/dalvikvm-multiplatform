import importlib.util
import json
from pathlib import Path


CASE_ROOT = Path(__file__).parents[1] / "cases" / "windows-libcore-smoke"
REPO_ROOT = Path(__file__).parents[2]


def _load_runner():
    spec = importlib.util.spec_from_file_location(
        "art_windows_libcore_gate", CASE_ROOT / "run.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load_runner()


def test_windows_libcore_runtime_matrix_matches_promoted_cases():
    matrix = runner.load_matrix()
    assert set(matrix) == {
        "AbsPathProbe",
        "BnProbe",
        "CoreProbe",
        "DnsProbe",
        "ExecProbe",
        "GcForced",
        "GcProbe",
        "GoldenApp",
        "InterruptProbe",
        "IoProbe",
        "Ipv6Probe",
        "LocaleProbe",
        "NetProbe",
        "OsErrnoProbe",
        "PathProbe",
        "PropsProbe",
        "RtMem",
        "ThreadStressProbe",
        "ThrowProbe",
        "UdpProbe",
        "ZipProbe",
    }
    assert matrix["ThrowProbe"]["require_nonzero"] is True
    assert matrix["LocaleProbe"]["expected_markers"] == [
        "locale.us=en-US",
        "case.us=ok",
        "date.iso.epoch=1970-01-01T00:00:00Z",
        "calendar.day1.ms=86400000",
        "tag.round=zh-Hans-CN",
        "LocaleProbe.done=ok",
    ]
    assert "udp.from=/127.0.0.1:" in matrix["UdpProbe"]["expected_markers"]
    assert matrix["ZipProbe"]["expected_markers"] == [
        "crc32=20adb109",
        "deflater.ok=true",
        "zis.entries=3",
        "zipfile.entries=3",
        "zip.cleanup=true",
        "ZipProbe.done=ok",
    ]
    assert matrix["BnProbe"]["expected_markers"] == [
        "BnProbe.done=ok sum=1111111110111111111011111111100 "
        "mod=9000000000900000000090 pow=483792039048379203904837920390"
    ]
    assert matrix["PathProbe"]["mode"] == "path"
    assert matrix["AbsPathProbe"]["mode"] == "absolute-path"
    assert all(case["expected_markers"] for case in matrix.values())
    assert all("AssertionError" in case["forbidden_markers"] for case in matrix.values())


def test_windows_libcore_runner_cleans_output_and_passes_explicit_contract(
    tmp_path, monkeypatch
):
    files = {}
    for name in ("dalvikvm.exe", "boot.jar", "coreprobe.jar", "icudt72l.dat"):
        path = tmp_path / name
        path.write_bytes(name.encode())
        files[name] = path
    work = tmp_path / "results" / "core"
    work.mkdir(parents=True)
    (work / "stale.txt").write_text("stale", encoding="utf-8")
    calls = []

    def fake_run_managed(**kwargs):
        calls.append(kwargs)
        kwargs["work_root"].mkdir(parents=True)
        (kwargs["work_root"] / "result.json").write_text(
            json.dumps({"main_class": kwargs["main_class"]}) + "\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(runner.runtime_gate, "run_managed", fake_run_managed)
    runner.run_gate(
        case="CoreProbe",
        target_id="windows-x86_64-msvc",
        dalvikvm=files["dalvikvm.exe"],
        boot_jar=files["boot.jar"],
        app_jar=files["coreprobe.jar"],
        work_root=work,
        icu_data=files["icudt72l.dat"],
        library_dirs=[tmp_path],
    )
    assert not (work / "stale.txt").exists()
    assert len(calls) == 1
    assert calls[0]["main_class"] == "CoreProbe"
    assert calls[0]["vm_options"] == ["-Xint"]
    assert calls[0]["require_nonzero"] is False
    assert "CoreProbe.done=ok" in calls[0]["expected"]


def test_windows_getnameinfo_uses_unicode_winsock_without_java_recursion():
    source = (
        REPO_ROOT / "tools" / "windows_x64" / "jni_stubs" / "win_net_natives.c"
    ).read_text(encoding="utf-8")
    start = source.index(
        "__declspec(dllexport) jstring Java_libcore_io_Linux_getnameinfo("
    )
    end = source.index(
        "__declspec(dllexport) jstring "
        "Java_libcore_io_Linux_getnameinfo__Ljava_net_InetAddress_2I(",
        start,
    )
    implementation = source[start:end]
    assert "GetNameInfoW(" in implementation
    assert "java_addr_to_sockaddr(" in implementation
    assert "getHostAddress" not in implementation
    assert "GetNameInfoA(" not in implementation


def test_windows_datagram_broadcast_maps_bionic_option_to_winsock():
    source = (
        REPO_ROOT / "tools" / "windows_x64" / "jni_stubs" / "win_net_natives.c"
    ).read_text(encoding="utf-8")
    assert "A_SO_BROADCAST = 6" in source
    set_start = source.index(
        "__declspec(dllexport) void Java_libcore_io_Linux_setsockoptInt("
    )
    set_end = source.index(
        "__declspec(dllexport) void "
        "Java_libcore_io_Linux_setsockoptInt__Ljava_io_FileDescriptor_2III(",
        set_start,
    )
    get_start = source.index(
        "__declspec(dllexport) jint Java_libcore_io_Linux_getsockoptInt("
    )
    get_end = source.index(
        "__declspec(dllexport) jint "
        "Java_libcore_io_Linux_getsockoptInt__Ljava_io_FileDescriptor_2II(",
        get_start,
    )
    assert "option == A_SO_BROADCAST) wopt = SO_BROADCAST" in source[
        set_start:set_end
    ]
    assert "option == A_SO_BROADCAST) wopt = SO_BROADCAST" in source[
        get_start:get_end
    ]


def test_path_probe_block_review_is_scoped_per_sample():
    output = """
---
in=C:\\x
path=C:\\x
prefixLength=3
isAbsolute=true
---
in=C:\\User/admin/.ssh/x
path=C:\\User\\admin\\.ssh\\x
isAbsolute=true
---
in=\\\\server\\share\\a
path=\\\\server\\share\\a
isAbsolute=true
"""
    assert runner._path_probe_block_failures(output) == []
    assert runner._path_probe_block_failures(output.replace("prefixLength=3", "")) == [
        "drive"
    ]
