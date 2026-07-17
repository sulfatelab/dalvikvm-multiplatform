"""Tests for the Layer 1 evaluator."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bp2cmake.config import Config
from bp2cmake.evaluator import Evaluator


def _ev(text, os_name=None, **cfg):
    if os_name is not None:
        cfg.setdefault("os", os_name)
    e = Evaluator(Config(**cfg))
    e.add_file(text, "<test>/Android.bp")
    return e


def test_variable_and_concat():
    e = _ev('''
        common = ["a.cpp", "b.cpp"]
        cc_library { name: "x", srcs: common + ["c.cpp"] }
    ''')
    m = e.resolve("x")
    assert m.srcs == ["a.cpp", "b.cpp", "c.cpp"]


def test_defaults_merge_lists_and_override_scalars():
    e = _ev('''
        cc_defaults {
            name: "d",
            cflags: ["-Wall"],
            srcs: ["base.cpp"],
        }
        cc_library {
            name: "x",
            defaults: ["d"],
            cflags: ["-Wextra"],
            srcs: ["x.cpp"],
        }
    ''')
    m = e.resolve("x")
    # defaults applied first, then own -> lists concatenate
    assert m.cflags == ["-Wall", "-Wextra"]
    assert m.srcs == ["base.cpp", "x.cpp"]


def test_target_linux_branch_selected():
    e = _ev('''
        cc_library {
            name: "x",
            srcs: ["common.cpp"],
            target: {
                linux: { srcs: ["errors_unix.cpp"] },
                darwin: { srcs: ["errors_unix.cpp"] },
                windows: { srcs: ["errors_windows.cpp"], enabled: true },
                android: { cflags: ["-D_FILE_OFFSET_BITS=64"] },
            },
        }
    ''')
    m = e.resolve("x")
    assert "errors_unix.cpp" in m.srcs          # linux branch active
    assert "common.cpp" in m.srcs
    assert "errors_windows.cpp" not in m.srcs   # windows dropped
    # android-only define dropped (re-adding it on Linux is a Layer 2 choice)
    assert "-D_FILE_OFFSET_BITS=64" not in m.cflags


def test_arch_select():
    e = _ev('''
        cc_library {
            name: "x",
            arch: {
                x86_64: { srcs: ["impl_x86.c"] },
                arm64: { srcs: ["impl_arm.c"] },
            },
        }
    ''', arch="x86_64")
    m = e.resolve("x")
    assert m.srcs == ["impl_x86.c"]


def test_exclude_srcs_effective():
    e = _ev('''
        cc_library {
            name: "x",
            srcs: ["a.cpp", "b.cpp", "c.cpp"],
            exclude_srcs: ["b.cpp"],
        }
    ''')
    m = e.resolve("x")
    assert m.effective_srcs() == ["a.cpp", "c.cpp"]


def test_gensrcs_resolution():
    e = _ev('''
        python_binary_host { name: "gen_tool", srcs: ["gen.py"] }
        gensrcs {
            name: "x_operator_srcs",
            cmd: "$(location gen_tool) some/dir $(in) > $(out)",
            tools: ["gen_tool"],
            srcs: ["a.h", "b.h"],
            output_extension: "operator_out.cc",
        }
    ''')
    gs = e.resolve_gensrcs("x_operator_srcs")
    assert gs.tool == "gen_tool"
    assert gs.srcs == ["a.h", "b.h"]
    assert gs.output_extension == "operator_out.cc"
    tool = e.tool_script("gen_tool")
    assert tool is not None and tool[1] == "gen.py"


def test_android_metadata_ignored():
    e = _ev('''
        cc_library {
            name: "x",
            srcs: ["a.cpp"],
            vndk: { enabled: true },
            apex_available: ["//apex_available:platform"],
            min_sdk_version: "29",
        }
    ''')
    m = e.resolve("x")
    assert "vndk" not in m.extra
    assert "apex_available" not in m.extra
    assert "min_sdk_version" not in m.extra


def test_soong_config_source_build_reenables():
    # Mirrors art_defaults: enabled:false unless source_build is true.
    e = _ev('''
        cc_defaults {
            name: "art_defaults",
            enabled: false,
            soong_config_variables: {
                source_build: { enabled: true },
            },
            cflags: ["-fno-rtti"],
        }
        cc_library { name: "x", defaults: ["art_defaults"], srcs: ["a.cc"] }
    ''')
    m = e.resolve("x")
    assert m.enabled is True          # source_build re-enabled it
    assert "-fno-rtti" in m.cflags


def test_codegen_select_enables_arch_siblings():
    # x86_64 build pulls x86_64 + x86 codegen branches (art.go default).
    e = _ev('''
        cc_library {
            name: "x",
            codegen: {
                x86_64: { srcs: ["cg_x86_64.cc"] },
                x86: { srcs: ["cg_x86.cc"] },
                arm64: { srcs: ["cg_arm64.cc"] },
            },
        }
    ''', arch="x86_64")
    m = e.resolve("x")
    assert "cg_x86_64.cc" in m.srcs
    assert "cg_x86.cc" in m.srcs       # 32-bit sibling included
    assert "cg_arm64.cc" not in m.srcs


def test_avx2_off_by_default():
    e = _ev('''
        cc_library {
            name: "x",
            arch: { x86_64: { avx2: { cflags: ["-mavx2"] } } },
        }
    ''', arch="x86_64")
    m = e.resolve("x")
    assert "-mavx2" not in m.cflags    # avx2 disabled by default

    e2 = Evaluator(Config(arch="x86_64", avx2=True))
    e2.add_file('cc_library { name: "x", arch: { x86_64: { avx2: { cflags: ["-mavx2"] } } } }', "<t>")
    assert "-mavx2" in e2.resolve("x").cflags


_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
LIBBASE_BP = os.path.join(_REPO, "vendor", "libbase", "Android.bp")


def test_real_libbase_resolution():
    if not os.path.exists(LIBBASE_BP):
        return
    e = Evaluator(Config())
    e.add_path(LIBBASE_BP, source_root=os.path.join(_REPO, "vendor"))
    m = e.resolve("libbase")

    srcs = m.effective_srcs()
    # The 16 common sources from libbase_defaults must all be present.
    for s in ["abi_compatibility.cpp", "cmsg.cpp", "file.cpp", "logging.cpp",
              "stringprintf.cpp", "strings.cpp", "test_utils.cpp"]:
        assert s in srcs, f"missing common src {s}"
    # The key fix: target.linux contributes errors_unix.cpp (archive cmake bug).
    assert "errors_unix.cpp" in srcs, "errors_unix.cpp should come from target.linux"
    # Windows-only sources must NOT appear.
    assert "errors_windows.cpp" not in srcs
    assert "utf8.cpp" not in srcs
    # cmsg.cpp must remain (it is only excluded on windows).
    assert "cmsg.cpp" in srcs
    # cppflags from libbase_defaults.
    assert "-Wexit-time-destructors" in m.cppflags
    # whole_static_libs picked up fmtlib.
    assert "fmtlib" in m.whole_static_libs
    # liblog is a shared_lib dep.
    assert "liblog" in m.shared_libs
    # libbase_headers reached via header_libs / export_header_lib_headers.
    assert "libbase_headers" in m.header_libs


# --- Soong select() expressions (new in android-16.0.0_r4) ----------------

def test_select_soong_config_default_branch():
    # An unset soong_config_variable resolves to the `default` arm.
    e = _ev('''
        cc_library {
            name: "x",
            srcs: ["base.cpp"] + select(soong_config_variable("art_module", "host_prefer_32_bit"), {
                true: [],
                default: ["dexlist.cpp"],
            }),
        }
    ''')
    m = e.resolve("x")
    assert m.srcs == ["base.cpp", "dexlist.cpp"]


def test_select_any_binding_unset_falls_to_default():
    # `any @ flag_val` must NOT match an unset variable; `default` wins.
    e = _ev('''
        cc_library {
            name: "x",
            cflags: ["-UNDEBUG"] + select(soong_config_variable("art_module", "art_debug_opt_flag"), {
                any @ flag_val: [flag_val],
                default: ["-Og"],
            }),
        }
    ''')
    m = e.resolve("x")
    assert m.cflags == ["-UNDEBUG", "-Og"]


def test_select_tuple_os_and_config():
    # select((os(), soong_config_variable(...)), { (pat,pat): val, ... })
    # host os == linux_glibc (not "android"), HAS_SANITIZE_HOST unset ->
    # the ("android", default) and (default, true) arms miss; (default,default) wins.
    e = _ev('''
        cc_library {
            name: "x",
            whole_static_libs: select((os(), soong_config_variable("ANDROID", "HAS_SANITIZE_HOST")), {
                ("android", default): [],
                (default, true): [],
                (default, default): ["libz"],
            }),
        }
    ''')
    m = e.resolve("x")
    assert m.whole_static_libs == ["libz"]


def test_select_release_flag_unset_default():
    e = _ev('''
        cc_library {
            name: "x",
            srcs: select(release_flag("RELEASE_SOMETHING"), {
                true: ["on.cpp"],
                default: ["off.cpp"],
            }),
        }
    ''')
    m = e.resolve("x")
    assert m.srcs == ["off.cpp"]


def test_select_enabled_scalar_default_true():
    # enabled: select(...) with unset var -> default true; module stays enabled.
    e = _ev('''
        cc_library {
            name: "x",
            srcs: ["a.cpp"],
            enabled: select(soong_config_variable("art_module", "art_build_host_debug"), {
                false: false,
                default: true,
            }),
        }
    ''')
    m = e.resolve("x")
    assert m.enabled is True


def test_strip_soong_dep_variant_tag():
    # android-16: shared_libs entries may carry a `#impl` variant tag.
    e = _ev('''
        cc_library {
            name: "x",
            shared_libs: ["libdexfile#impl", "libnativehelper#impl", "liblog"],
            static_libs: ["libfoo#bootstrap"],
            header_libs: ["libbar#impl"],
        }
    ''')
    m = e.resolve("x")
    assert m.shared_libs == ["libdexfile", "libnativehelper", "liblog"]
    assert m.static_libs == ["libfoo"]
    assert m.header_libs == ["libbar"]


def test_target_windows_branch_selected():
    e = _ev('''
        cc_library {
            name: "x",
            srcs: ["common.cpp"],
            target: {
                linux: { srcs: ["errors_unix.cpp"] },
                windows: { srcs: ["errors_windows.cpp"], enabled: true },
                android: { cflags: ["-DANDROID"] },
            },
        }
    ''', os_name="windows")
    m = e.resolve("x")
    assert "errors_windows.cpp" in m.srcs
    assert "common.cpp" in m.srcs
    assert "errors_unix.cpp" not in m.srcs
    assert "-DANDROID" not in m.cflags


def test_not_windows_dropped_on_windows_config():
    e = _ev('''
        cc_library {
            name: "x",
            srcs: ["common.cpp"],
            target: {
                not_windows: { srcs: ["unix_only.cpp"] },
                windows: { srcs: ["win_only.cpp"] },
            },
        }
    ''', os_name="windows")
    m = e.resolve("x")
    assert "win_only.cpp" in m.srcs
    assert "unix_only.cpp" not in m.srcs
