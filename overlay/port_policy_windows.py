# Port-policy overlay (Layer 2) for MinDalvikVM **Win64**.
# Use: python3 -m bp2cmake --os windows --overlay overlay/port_policy_windows.py ...
#
# Phase 0: foundational -> libartbase
# Phase 1: libart-runtime + dalvikvm skeleton (-showversion)

from bp2cmake.overlay import GlobalPolicy, ModulePolicy, Overlay

_FORCE = dict(force_enabled=True)

_ART_PUB = [
    "ART_STACK_OVERFLOW_GAP_arm=8192",
    "ART_STACK_OVERFLOW_GAP_arm64=8192",
    "ART_STACK_OVERFLOW_GAP_riscv64=8192",
    "ART_STACK_OVERFLOW_GAP_x86=8192",
    "ART_STACK_OVERFLOW_GAP_x86_64=8192",
    "ART_FRAME_SIZE_LIMIT=1744",
]

_ART_TARGET = [
    "ART_TARGET",
    "ART_TARGET_WINDOWS",
    "ART_DEFAULT_GC_TYPE_IS_CMS",
    "USE_D8_DESUGAR=1",
]

_WIN_CFLAGS = [
    "-Wno-thread-safety",
    "-Wno-unused-command-line-argument",
    "-Wno-microsoft-cast",
]

OVERLAY = Overlay(
    global_policy=GlobalPolicy(
        name_map={
            "libbase": "base",
            "liblog": "log",
            "libz": "z",
            "liblz4": "lz4",
            "liblzma": "lzma",
            "libnativehelper": "nativehelper",
            "libexpat": "expat",
            "libcap": "cap",
        },
        host_libs=["libz", "liblz4", "libcap", "libexpat"],
        drop_cflags=[
            "-Werror", "-Wthread-safety", "-Wmissing-noreturn",
            "-fvisibility=protected",
            "-Wl,--exclude-libs=libziparchive.a",
        ],
        drop_ldflags=[
            "-z max-page-size=0x200000",
            "-Wl,--exclude-libs=libziparchive.a",
            "-Wl,--export-dynamic", "-pie",
            "-static-libgcc", "-static-libstdc++",
            "-Wl,-z,global",
        ],
        drop_ldflags_containing=["art_common/out", "--enable-new-dtags", "Wl,-z,", "-z ", "max-page-size", "z,max-page-size"],
        art_defines=_ART_PUB + [
            "ART_PAGE_SIZE_AGNOSTIC=1",
            "ART_DEFAULT_GC_TYPE_IS_CMS",
        ],
        strip_lib_prefix=True,
    ),
    modules={
        # --- Phase 0 foundational ------------------------------------------
        "libbase": ModulePolicy(
            kind="shared", absorb_whole_static=True,
            add_cppflags=["-Wno-deprecated-declarations"],
            add_cflags=_WIN_CFLAGS,
            add_defines=["_CRT_SECURE_NO_WARNINGS"],
            force_enabled=True,
        ),
        "liblog": ModulePolicy(
            kind="shared",
            remove_srcs=["logprint.cpp", "event_tag_map.cpp", "logger_name.cpp"],
            add_defines=["_CRT_SECURE_NO_WARNINGS"],
            force_enabled=True,
        ),
        "libnativehelper": ModulePolicy(
            kind="shared", set_c_std="c11",
            add_defines=["_CRT_SECURE_NO_WARNINGS"],
            force_enabled=True,
        ),
        "libziparchive": ModulePolicy(
            kind="shared", add_compat_include_dirs=["."],
            add_defines=["_CRT_SECURE_NO_WARNINGS"],
            force_enabled=True,
        ),
        "libtinyxml2": ModulePolicy(
            kind="shared", remove_shared_libs=["liblog"], force_enabled=True,
        ),
        "libartpalette": ModulePolicy(
            kind="shared",
            add_shared_libs=["libbase", "liblog"],
            remove_static_libs=["libbase", "liblog"],
            force_enabled=True,
        ),
        "libartbase": ModulePolicy(
            kind="static", absorb_whole_static=True,
            remove_static_libs=[
                "art-aconfig-flags-lib", "art-aconfig-rw-flags-lib",
                "libaconfig_storage_read_api_cc", "libcore-aconfig-flags-native-lib",
                "libcap", "libziparchive", "libz", "liblog", "libartpalette", "libbase",
            ],
            add_shared_libs=["libziparchive", "libz", "liblog", "libartpalette", "libbase"],
            add_public_defines=_ART_PUB,
            add_cflags=_WIN_CFLAGS,
            add_defines=["_CRT_SECURE_NO_WARNINGS"],
            add_gensrc_includes=["art/aconfig/include"],
            force_enabled=True,
        ),
        "libprocinfo": ModulePolicy(
            kind="shared", force_enabled=True,
            remove_srcs=["process.cpp"],  # Linux /proc only; stub via harness
        ),
        "liblzma": ModulePolicy(
            kind="shared", force_enabled=True,
            # AesOpt.c uses MSVC __m128i field access; skip Intel AES-NI opt on Win64 clang.
            remove_srcs=["AesOpt.c"],
        ),
        "libcpu_features": ModulePolicy(
            kind="static", absorb_whole_static=True,
            add_defines=["HAVE_STRONG_GETAUXVAL", "HAVE_DLFCN_H"],
            force_enabled=True,
        ),

        # --- Phase 1 runtime graph ----------------------------------------
        "libdexfile": ModulePolicy(
            kind="static", force_enabled=True,
            add_srcs=["external/dex_file_supp.cc"],
            add_public_defines=_ART_PUB,
            add_cflags=_WIN_CFLAGS,
        ),
        "libelffile": ModulePolicy(
            kind="static", force_enabled=True, add_cflags=_WIN_CFLAGS,
        ),
        "libprofile": ModulePolicy(
            kind="static", force_enabled=True, add_cflags=_WIN_CFLAGS,
        ),
        "libsigchain": ModulePolicy(
            kind="shared", force_enabled=True,
            # Layer 1 may select sigchain.cc; strip it. Harness adds
            # vendor/art/runtime/multiplatform/windows/sigchain_windows.cc as the only source.
            remove_srcs=["sigchain.cc", "sigchain_fake.cc"],
            add_defines=["CHAR_BIT=8", "_CRT_SECURE_NO_WARNINGS"],
            add_cflags=_WIN_CFLAGS,
        ),
        "libnativebridge": ModulePolicy(
            kind="shared", force_enabled=True, add_cflags=_WIN_CFLAGS,
        ),
        "libnativeloader": ModulePolicy(
            kind="shared", force_enabled=True, add_cflags=_WIN_CFLAGS,
        ),
        "libodrstatslog": ModulePolicy(
            kind="static", force_enabled=True, add_cflags=_WIN_CFLAGS,
        ),
        "libunwindstack": ModulePolicy(
            kind="static", force_enabled=True, set_cpp_std="gnu++20",
            remove_static_libs=["libdexfile_support", "librustc_demangle_static"],
            add_shared_libs=["libdexfile"],
            add_cflags=_WIN_CFLAGS,
            # Linux GAS; inject C stub from harness.
            remove_srcs=["AsmGetRegsX86_64.S", "AsmGetRegsX86.S", "AsmGetRegsArm.S", "AsmGetRegsArm64.S"],
        ),
        "libart-disassembler": ModulePolicy(
            kind="shared", force_enabled=True, add_cflags=_WIN_CFLAGS,
        ),
        "libart-compiler": ModulePolicy(
            kind="static", force_enabled=True, add_cflags=_WIN_CFLAGS,
            add_defines=["_CRT_SECURE_NO_WARNINGS"],
        ),
        # Core runtime static library (host picks monitor_linux etc.; we swap OS files in harness)
        "libart-runtime": ModulePolicy(
            kind="static", force_enabled=True, absorb_whole_static=True,
            remove_srcs=[
                "monitor_linux.cc", "runtime_linux.cc", "thread_linux.cc",
            ],
            add_cflags=_WIN_CFLAGS + ["-fno-delete-null-pointer-checks"],
            add_defines=["_CRT_SECURE_NO_WARNINGS", "BUILDING_LIBART"],
            add_public_defines=_ART_TARGET + _ART_PUB,
            add_include_dirs=["external/cpu_features/include"],
            add_gensrc_includes=["art/asm/include", "art/aconfig/include"],
            add_gensrc_sources=["art/asm/mterp/mterp_x86_64.S"],
        ),
        "libart": ModulePolicy(
            kind="shared", force_enabled=True,
            absorb_whole_static=True,  # fold libart-runtime + libart-compiler
            # Host OS files come via absorbed libart-runtime; drop Linux ones.
            # Windows replacements are injected by the Phase 1 CMake harness
            # from vendor/art/runtime/multiplatform/windows/ and openjdkjvm/.
            remove_srcs=[
                "monitor_linux.cc", "runtime_linux.cc", "thread_linux.cc",
            ],
            add_cflags=_WIN_CFLAGS,
            add_public_defines=_ART_TARGET + _ART_PUB,
            add_defines=[
                "ART_BASE_ADDRESS=0x60000000",
                "ART_BASE_ADDRESS_MIN_DELTA=(-0x1000000)",
                "ART_BASE_ADDRESS_MAX_DELTA=0x1000000",
                "BUILDING_LIBART",
                "_CRT_SECURE_NO_WARNINGS",
            ] + _ART_PUB,
            add_include_dirs=["external/cpu_features/include"],
            add_gensrc_includes=["art/asm/include", "art/aconfig/include"],
            add_gensrc_sources=["art/asm/mterp/mterp_x86_64.S"],
        ),
        "dalvikvm": ModulePolicy(
            kind="executable", force_enabled=True,
            absorb_whole_static=False,
            add_shared_libs=["libart", "libsigchain", "liblog", "libnativehelper"],
            add_cflags=_WIN_CFLAGS + [],
            add_defines=["_CRT_SECURE_NO_WARNINGS"],
        ),
    },
)
