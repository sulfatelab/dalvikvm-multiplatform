"""Unified target-aware policy for the generated ART product graph.

Layer 1 resolves Android.bp for a canonical target profile. This Layer 2 file
then composes policy that is genuinely common to the Linux and Windows product
with a small, explicit delta for the selected target platform. Layer 3 emits
the resulting target-resolved CMake graph.

The currently generatable profiles are linux-x86_64-gnu and
windows-x86_64-msvc. Their x86-64 source selections remain visible in the
target deltas so future architecture admission cannot inherit them silently.
"""

from __future__ import annotations

from bp2cmake.overlay import BlueprintScanPolicy, GlobalPolicy, ModulePolicy, Overlay
from bp2cmake.target import TargetProfile


_ART_GAPS = [
    "ART_STACK_OVERFLOW_GAP_arm=8192",
    "ART_STACK_OVERFLOW_GAP_arm64=8192",
    "ART_STACK_OVERFLOW_GAP_riscv64=8192",
    "ART_STACK_OVERFLOW_GAP_x86=8192",
    "ART_STACK_OVERFLOW_GAP_x86_64=8192",
    "ART_FRAME_SIZE_LIMIT=1744",
]

_ART_BASE_ADDRESSES = [
    "ART_BASE_ADDRESS=0x60000000",
    "ART_BASE_ADDRESS_MIN_DELTA=(-0x1000000)",
    "ART_BASE_ADDRESS_MAX_DELTA=0x1000000",
]

_WINDOWS_ART_TARGET = [
    "ART_TARGET",
    "ART_TARGET_WINDOWS",
    "ART_DEFAULT_GC_TYPE_IS_CMS",
    "USE_D8_DESUGAR=1",
]

_WINDOWS_CFLAGS = [
    "-Wno-thread-safety",
    "-Wno-unused-command-line-argument",
    "-Wno-microsoft-cast",
]

_COMMON_NAME_MAP = {
    "libbase": "base",
    "liblog": "log",
    "libz": "z",
    "liblz4": "lz4",
    "liblzma": "lzma",
    "libnativehelper": "nativehelper",
    "libexpat": "expat",
}

_PRODUCT_BLUEPRINT_SCAN = BlueprintScanPolicy(
    excluded_path_components=("test", "tests", "fuzz", "benchmark", "sample"),
    excluded_top_levels=(("MDVM_NATIVE_SRC_ROOT_DIR", ("art",)),),
)


def _global_policy(profile: TargetProfile) -> GlobalPolicy:
    """Compose cross-module policy without hiding target-specific flags."""
    common = dict(
        name_map=dict(_COMMON_NAME_MAP),
        host_libs=["libz", "liblz4", "libcap", "libexpat"],
        drop_cflags=[
            "-Werror",
            "-Wthread-safety",
            "-Wmissing-noreturn",
            "-fvisibility=protected",
        ],
        art_defines=_ART_GAPS
        + ["ART_PAGE_SIZE_AGNOSTIC=1", "ART_DEFAULT_GC_TYPE_IS_CMS"],
        drop_ldflags=["-Wl,--exclude-libs=libziparchive.a"],
        drop_ldflags_containing=["art_common/out", "--enable-new-dtags"],
    )
    if profile.target_platform == "linux":
        return GlobalPolicy(**common)
    if profile.target_platform == "windows":
        common["name_map"] = {**_COMMON_NAME_MAP, "libcap": "cap"}
        if profile.target_arch in ("x86_64", "aarch64", "arm64ec"):
            # ART uses __LP64__ as its 64-bit pointer-layout selector even on
            # Windows LLP64 targets where Clang does not define it itself.
            # Keep that ABI contract in target policy rather than inheriting
            # it from the temporary compatibility prelude.
            common["art_defines"] = [*common["art_defines"], "__LP64__=1"]
        common["drop_cflags"] = [
            "-Werror",
            "-Wthread-safety",
            "-Wmissing-noreturn",
            "-fvisibility=protected",
            "-Wl,--exclude-libs=libziparchive.a",
        ]
        common["drop_ldflags"] = [
            "-z max-page-size=0x200000",
            "-Wl,--exclude-libs=libziparchive.a",
            "-Wl,--export-dynamic",
            "-pie",
            "-static-libgcc",
            "-static-libstdc++",
            "-Wl,-z,global",
        ]
        common["drop_ldflags_containing"] = [
            "art_common/out",
            "--enable-new-dtags",
            "Wl,-z,",
            "-z ",
            "max-page-size",
            "z,max-page-size",
        ]
        # ART's long-jump/deoptimization path cannot synchronize a CET shadow
        # stack. Every generated PE must advertise that process contract.
        common["add_ldflags"] = [
            "LINKER:/CETCOMPAT:NO",
            "LINKER:/DYNAMICBASE",
            "LINKER:/NXCOMPAT",
        ]
        if profile.target_arch in ("x86_64", "aarch64", "arm64ec"):
            common["add_ldflags"].append("LINKER:/HIGHENTROPYVA")
        return GlobalPolicy(**common)
    raise ValueError(f"no ART overlay policy for target {profile.target_id!r}")


# Fields in this table are byte-for-byte equal in both admitted product
# policies. A target delta replaces a whole field only when semantics differ;
# list merging is deliberately forbidden so ordering remains reviewable.
_COMMON_MODULES: dict[str, dict[str, object]] = {
    "dalvikvm": dict(kind="executable", absorb_whole_static=False),
    "dex2oat": dict(
        kind="executable",
        absorb_whole_static=False,
        add_shared_libs=[
            "libart-dex2oat",
            "libart-compiler",
            "libart",
            "libartbase",
            "libdexfile",
            "libprofile",
            "libartpalette",
            "libelffile",
        ],
        remove_static_libs=["libdex2oat_static"],
    ),
    "libart": dict(
        kind="shared",
        add_include_dirs=["external/cpu_features/include"],
    ),
    # ART keeps compiler objects in the runtime for JIT, while the separately
    # compiled DSO gives dex2oat equal shared-library topology on both targets.
    "libart-compiler": dict(
        kind="shared",
        add_shared_libs=["libart", "libart-disassembler"],
    ),
    "libart-dex2oat": dict(
        kind="shared",
        add_shared_libs=["libart-compiler"],
    ),
    "libart-disassembler": dict(kind="shared"),
    "libartbase": dict(add_public_defines=_ART_GAPS),
    "libartpalette": dict(
        kind="shared",
        add_shared_libs=["libbase", "liblog"],
    ),
    "libbase": dict(
        kind="shared",
        add_cppflags=["-Wno-deprecated-declarations"],
    ),
    "libcpu_features": dict(
        kind="static",
        add_defines=["HAVE_STRONG_GETAUXVAL", "HAVE_DLFCN_H"],
    ),
    "libdexfile": dict(add_srcs=["external/dex_file_supp.cc"]),
    "libicu": dict(
        kind="shared",
        add_defines=["U_SHOW_CPLUSPLUS_API=0", "__INTRODUCED_IN(x)="],
    ),
    "libicu_jni": dict(
        kind="shared",
        add_defines=[
            "U_USING_ICU_NAMESPACE=0",
            "ANDROID_LINK_SHARED_ICU4C",
            "__INTRODUCED_IN(x)=",
        ],
    ),
    # Keep the product TLS topology equal across target platforms. Conscrypt's
    # platform JNI is always a DSO and consumes the shared BoringSSL DSOs;
    # target policy may still select architecture-specific BoringSSL sources.
    "libcrypto": dict(kind="shared"),
    "libssl": dict(kind="shared"),
    "libjavacrypto": dict(
        kind="shared",
        remove_static_libs=["libcrypto", "libssl"],
        add_shared_libs=["libcrypto", "libssl"],
    ),
    "libjavacore": dict(
        kind="shared",
        remove_static_libs=["libnativehelper_compat_libc++"],
    ),
    "liblog": dict(kind="shared"),
    "liblzma": dict(kind="shared"),
    "libnativebridge": dict(kind="shared"),
    "libnativehelper": dict(kind="shared"),
    "libnativeloader": dict(kind="shared"),
    "libopenjdk": dict(
        kind="shared",
        remove_static_libs=["libnativehelper_compat_libc++"],
    ),
    "libopenjdkjvm": dict(kind="shared"),
    "libopenjdkjvmti": dict(kind="shared"),
    "libprocinfo": dict(kind="shared"),
    "libsigchain": dict(kind="shared"),
    "libtinyxml2": dict(
        kind="shared",
        remove_shared_libs=["liblog"],
    ),
    "libunwindstack": dict(
        add_shared_libs=["libdexfile"],
        remove_static_libs=["libdexfile_support", "librustc_demangle_static"],
        set_cpp_std="gnu++20",
    ),
    "libziparchive": dict(
        kind="shared",
        add_compat_include_dirs=["."],
    ),
}


_LINUX_MODULE_DELTA: dict[str, dict[str, object]] = {
    "dalvikvm": dict(
        add_shared_libs=["libart", "libsigchain"],
        add_cflags=["-fPIC"],
        add_ldflags=["-pie"],
    ),
    "dex2oat": dict(add_cflags=["-fPIC"], add_ldflags=["-pie"]),
    "libandroidicuinit": dict(kind="static", add_cflags=["-fPIC"]),
    "libandroidio": dict(kind="shared"),
    "libart": dict(
        add_defines=_ART_BASE_ADDRESSES + _ART_GAPS,
        add_public_defines=[
            "ART_DEFAULT_GC_TYPE_IS_CMS",
            "USE_D8_DESUGAR=1",
            "ART_TARGET",
            "ART_TARGET_LINUX",
        ],
        add_gensrc_includes=["art/asm/include"],
    ),
    "libartbase": dict(
        kind="shared",
        remove_static_libs=[
            "art-aconfig-flags-lib",
            "art-aconfig-rw-flags-lib",
            "libaconfig_storage_read_api_cc",
            "libcore-aconfig-flags-native-lib",
        ],
    ),
    "libbase": dict(add_defines=["_FILE_OFFSET_BITS=64"]),
    # bcm_object is expanded by Layer 1 after Blueprint target/architecture
    # selection. Do not duplicate its assembly list here: each future target
    # must receive the source set declared by BoringSSL itself.
    "libcrypto": dict(
        kind="shared",
        add_cflags=[
            "-fPIC",
            "-fvisibility=hidden",
            "-Wno-unused-parameter",
            "-Wno-deprecated-declarations",
        ],
        add_defines=[
            "BORINGSSL_SHARED_LIBRARY",
            "BORINGSSL_ANDROID_SYSTEM",
            "OPENSSL_SMALL",
        ],
        add_public_defines=["BORINGSSL_IMPLEMENTATION"],
    ),
    "libcrypto_static": dict(
        kind="static",
        add_cflags=[
            "-fPIC",
            "-fvisibility=hidden",
            "-Wno-unused-parameter",
            "-Wno-deprecated-declarations",
        ],
        add_defines=["BORINGSSL_ANDROID_SYSTEM", "OPENSSL_SMALL"],
        add_public_defines=["BORINGSSL_IMPLEMENTATION"],
    ),
    "libdexfile": dict(kind="shared"),
    "libelffile": dict(add_cflags=["-fPIC"]),
    "libfdlibm": dict(
        add_cflags=["-fPIC"],
        add_defines=["_IEEE_LIBM", "__LITTLE_ENDIAN"],
    ),
    "libicu": dict(add_cflags=["-fvisibility=protected"]),
    "libicu_jni": dict(
        add_cflags=["-fvisibility=protected", "-Wno-unused-parameter"]
    ),
    # This is an ART product target, not Conscrypt's OpenJDK host JNI. Select
    # the JNIEnv** Android native boundary even though the OS target is Linux.
    "libjavacrypto": dict(add_defines=["ANDROID"]),
    "libicui18n": dict(
        kind="shared",
        add_cflags=[
            "-fPIC",
            "-fvisibility=hidden",
            "-frtti",
            "-Wno-unused-parameter",
            "-Wno-deprecated-declarations",
        ],
        add_defines=["U_I18N_IMPLEMENTATION", "PIC", "_REENTRANT"],
    ),
    "libicuuc": dict(
        kind="shared",
        add_cflags=[
            "-fPIC",
            "-fvisibility=hidden",
            "-frtti",
            "-Wno-unused-parameter",
            "-Wno-deprecated-declarations",
        ],
        add_defines=["U_COMMON_IMPLEMENTATION", "PIC", "_REENTRANT"],
    ),
    "libicuuc_stubdata": dict(kind="static", add_cflags=["-fPIC"]),
    "libjavacore": dict(
        add_cflags=[
            "-fvisibility=protected",
            "-Wno-unused-parameter",
            "-Wno-unused-variable",
            "-Wno-parentheses-equality",
            "-Wno-constant-logical-operand",
            "-Wno-sometimes-uninitialized",
        ],
        add_defines=[
            "U_USING_ICU_NAMESPACE=0",
            "__GLIBC__",
            "_LARGEFILE64_SOURCE",
            "_GNU_SOURCE",
            "LINUX",
            "__INTRODUCED_IN(x)=",
            "LIBICU_U_SHOW_CPLUSPLUS_API=1",
        ],
        add_include_dirs=["external/boringssl/src/include"],
    ),
    "liblog": dict(remove_srcs=["logprint.cpp", "event_tag_map.cpp"]),
    "libnativehelper": dict(set_c_std="gnu11"),
    "libodrstatslog": dict(add_cflags=["-fPIC"]),
    "libopenjdk": dict(
        add_cflags=["-fvisibility=protected", "-Wno-unused-parameter"],
        add_defines=[
            "U_USING_ICU_NAMESPACE=0",
            "__GLIBC__",
            "_LARGEFILE64_SOURCE",
            "_GNU_SOURCE",
            "LINUX",
            "__INTRODUCED_IN(x)=",
        ],
        add_include_dirs=["external/boringssl/src/include"],
    ),
    "libprofile": dict(kind="shared"),
    "libsigchain": dict(add_defines=["CHAR_BIT=8"]),
    "libunwindstack": dict(kind="shared"),
}


_WINDOWS_MODULE_DELTA: dict[str, dict[str, object]] = {
    "dalvikvm": dict(
        add_shared_libs=["libart", "libsigchain", "liblog", "libnativehelper"],
        add_cflags=_WINDOWS_CFLAGS,
        add_defines=["_CRT_SECURE_NO_WARNINGS"],
        force_enabled=True,
    ),
    "dex2oat": dict(
        add_cflags=_WINDOWS_CFLAGS,
        add_defines=[
            "_CRT_SECURE_NO_WARNINGS",
            "ART_CONSUMING_LIBART",
            "MDVM_WINDOWS_DEX2OAT_COMPAT",
        ],
        force_enabled=True,
    ),
    "libart": dict(
        remove_srcs=["monitor_linux.cc", "runtime_linux.cc", "thread_linux.cc"],
        add_cflags=_WINDOWS_CFLAGS,
        add_defines=_ART_BASE_ADDRESSES
        + ["BUILDING_LIBART", "_CRT_SECURE_NO_WARNINGS"]
        + _ART_GAPS,
        add_public_defines=_WINDOWS_ART_TARGET + _ART_GAPS,
        add_gensrc_includes=["art/asm/include", "art/aconfig/include"],
        force_enabled=True,
    ),
    "libart-compiler": dict(
        add_cflags=_WINDOWS_CFLAGS,
        add_defines=["_CRT_SECURE_NO_WARNINGS"],
        force_enabled=True,
    ),
    "libart-dex2oat": dict(
        add_cflags=_WINDOWS_CFLAGS,
        add_defines=[
            "_CRT_SECURE_NO_WARNINGS",
            "ART_CONSUMING_LIBART",
            "MDVM_WINDOWS_DEX2OAT_COMPAT",
        ],
        force_enabled=True,
    ),
    "libart-disassembler": dict(
        add_cflags=_WINDOWS_CFLAGS,
        force_enabled=True,
    ),
    "libart-runtime": dict(
        kind="static",
        remove_srcs=["monitor_linux.cc", "runtime_linux.cc", "thread_linux.cc"],
        add_cflags=_WINDOWS_CFLAGS + ["-fno-delete-null-pointer-checks"],
        add_defines=["_CRT_SECURE_NO_WARNINGS", "BUILDING_LIBART"],
        add_public_defines=_WINDOWS_ART_TARGET + _ART_GAPS,
        add_include_dirs=["external/cpu_features/include"],
        add_gensrc_includes=["art/asm/include", "art/aconfig/include"],
        force_enabled=True,
    ),
    "libartbase": dict(
        kind="static",
        add_shared_libs=["libziparchive", "libz", "liblog", "libartpalette", "libbase"],
        remove_static_libs=[
            "art-aconfig-flags-lib",
            "art-aconfig-rw-flags-lib",
            "libaconfig_storage_read_api_cc",
            "libcore-aconfig-flags-native-lib",
            "libcap",
            "libziparchive",
            "libz",
            "liblog",
            "libartpalette",
            "libbase",
        ],
        add_cflags=_WINDOWS_CFLAGS,
        add_defines=["_CRT_SECURE_NO_WARNINGS"],
        add_gensrc_includes=["art/aconfig/include"],
        force_enabled=True,
    ),
    "libartpalette": dict(
        remove_static_libs=["libbase", "liblog"],
        force_enabled=True,
    ),
    "libbase": dict(
        add_cflags=_WINDOWS_CFLAGS,
        add_defines=["_CRT_SECURE_NO_WARNINGS"],
        force_enabled=True,
    ),
    "libcpu_features": dict(force_enabled=True),
    "libdexfile": dict(
        kind="static",
        add_cflags=_WINDOWS_CFLAGS,
        add_public_defines=_ART_GAPS,
        force_enabled=True,
    ),
    "libelffile": dict(
        kind="static",
        add_cflags=_WINDOWS_CFLAGS,
        force_enabled=True,
    ),
    "libicu": dict(force_enabled=True),
    "libicu_jni": dict(add_cflags=_WINDOWS_CFLAGS, force_enabled=True),
    "libcrypto": dict(
        add_cflags=_WINDOWS_CFLAGS
        + [
            "-fvisibility=hidden",
            "-Wno-unused-parameter",
            "-Wno-deprecated-declarations",
            "-Wno-bitwise-op-parentheses",
            "-Wno-unknown-pragmas",
        ],
        add_defines=[
            "BORINGSSL_SHARED_LIBRARY",
            "BORINGSSL_ANDROID_SYSTEM",
            "BORINGSSL_IMPLEMENTATION",
            "OPENSSL_NO_ASM",
            "OPENSSL_SMALL",
        ],
        add_shared_libs=["bcrypt", "advapi32"],
        force_enabled=True,
    ),
    "libssl": dict(
        add_cflags=_WINDOWS_CFLAGS + ["-Wno-unused-parameter"],
        add_defines=["OPENSSL_NO_ASM"],
        force_enabled=True,
    ),
    "libjavacrypto": dict(
        add_cflags=_WINDOWS_CFLAGS
        + ["-Wno-unused-parameter", "-Wno-sign-compare"],
        # app_data.h includes ws2ipdef.h directly. The Windows SDK expects the
        # minwindef CONST spelling that project compatibility headers normally
        # hide from C++ sources, so preserve it only for this boundary DSO.
        add_defines=[
            "CONSCRYPT_OPENJDK",
            "OPENSSL_NO_ASM",
            "CONST=const",
            "MDVM_WINDOWS_KEEP_CONST_MACRO=1",
        ],
        force_enabled=True,
    ),
    "libjavacore": dict(
        remove_srcs=[
            "libcore_io_Linux.cpp",
            "cbigint.cpp",
            "android_system_OsConstantsHolder.cpp",
        ],
        add_shared_libs=["libicuuc", "libicui18n", "libopenjdkjvm"],
        add_cflags=_WINDOWS_CFLAGS,
        add_defines=[
            "U_USING_ICU_NAMESPACE=0",
            "ANDROID_LINK_SHARED_ICU4C",
            "LIBICU_U_SHOW_CPLUSPLUS_API=1",
            "MDVM_WINDOWS_KEEP_CONST_MACRO",
            "__INTRODUCED_IN(x)=",
        ],
        force_enabled=True,
    ),
    "liblog": dict(
        remove_srcs=["logprint.cpp", "event_tag_map.cpp", "logger_name.cpp"],
        add_defines=["_CRT_SECURE_NO_WARNINGS"],
        force_enabled=True,
    ),
    "liblzma": dict(remove_srcs=["AesOpt.c"], force_enabled=True),
    "libnativebridge": dict(add_cflags=_WINDOWS_CFLAGS, force_enabled=True),
    "libnativehelper": dict(
        add_defines=["_CRT_SECURE_NO_WARNINGS"],
        set_c_std="c11",
        force_enabled=True,
    ),
    "libnativeloader": dict(add_cflags=_WINDOWS_CFLAGS, force_enabled=True),
    "libodrstatslog": dict(
        kind="static",
        add_cflags=_WINDOWS_CFLAGS,
        force_enabled=True,
    ),
    "libopenjdk": dict(
        remove_srcs=[
            "linux_close.cpp",
            "NativeThread.c",
            "OnLoad.cpp",
            "LinuxNativeDispatcher.c",
            "LinuxWatchService.c",
            "UnixCopyFile.c",
            "UnixNativeDispatcher.c",
            "UNIXProcess_md.c",
            "EPollPort.c",
            "UnixAsynchronousServerSocketChannelImpl.c",
            "UnixAsynchronousSocketChannelImpl.c",
            "FileSystemPreferences.c",
            "UnixDomainSockets.c",
            "UnixFileSystem_md.c",
            "System.c",
            "Runtime.c",
        ],
        add_shared_libs=["libicuuc", "libopenjdkjvm"],
        add_cflags=_WINDOWS_CFLAGS,
        add_defines=["U_USING_ICU_NAMESPACE=0", "_LP64=1", "__INTRODUCED_IN(x)="],
        force_enabled=True,
    ),
    "libopenjdkjvm": dict(
        add_cflags=_WINDOWS_CFLAGS,
        add_defines=["ART_CONSUMING_LIBART", "MDVM_SOCKET_FD_REGISTRY_EXPORTS=1"],
        force_enabled=True,
    ),
    "libopenjdkjvmti": dict(
        add_cflags=_WINDOWS_CFLAGS,
        add_defines=["ART_CONSUMING_LIBART", "_CRT_SECURE_NO_WARNINGS"],
        force_enabled=True,
    ),
    "libprocinfo": dict(remove_srcs=["process.cpp"], force_enabled=True),
    "libprofile": dict(
        kind="static",
        add_cflags=_WINDOWS_CFLAGS,
        force_enabled=True,
    ),
    "libsigchain": dict(
        remove_srcs=["sigchain.cc", "sigchain_fake.cc"],
        add_cflags=_WINDOWS_CFLAGS,
        add_defines=["CHAR_BIT=8", "_CRT_SECURE_NO_WARNINGS"],
        force_enabled=True,
    ),
    "libtinyxml2": dict(force_enabled=True),
    "libunwindstack": dict(
        kind="static",
        remove_srcs=[
            "AsmGetRegsX86_64.S",
            "AsmGetRegsX86.S",
            "AsmGetRegsArm.S",
            "AsmGetRegsArm64.S",
        ],
        add_cflags=_WINDOWS_CFLAGS,
        force_enabled=True,
    ),
    "libziparchive": dict(
        add_defines=["_CRT_SECURE_NO_WARNINGS"],
        force_enabled=True,
    ),
}


def _module_policies(
    profile: TargetProfile, delta: dict[str, dict[str, object]]
) -> dict[str, ModulePolicy]:
    names = list(_COMMON_MODULES)
    names.extend(name for name in delta if name not in _COMMON_MODULES)
    policies = {
        name: ModulePolicy(**{**_COMMON_MODULES.get(name, {}), **delta.get(name, {})})
        for name in names
    }
    generated_mterp = f"art/asm/mterp/{profile.mterp_output}"
    for name in ("libart", "libart-runtime"):
        if name in policies:
            policies[name].add_gensrc_sources = [generated_mterp]
    return policies


def make_overlay(profile: TargetProfile) -> Overlay:
    if profile.target_id == "linux-x86_64-gnu":
        delta = _LINUX_MODULE_DELTA
    elif profile.target_id == "windows-x86_64-msvc":
        delta = _WINDOWS_MODULE_DELTA
    else:
        raise ValueError(
            f"no reviewed ART overlay policy for target {profile.target_id!r}"
        )
    return Overlay(
        global_policy=_global_policy(profile),
        modules=_module_policies(profile, delta),
        blueprint_scan=_PRODUCT_BLUEPRINT_SCAN,
    )
