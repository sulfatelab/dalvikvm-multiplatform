# Port-policy overlay (Layer 2) for the MinDalvikVM Linux/glibc build.
#
# This file is the durable, human-owned record of every DELIBERATE deviation
# from what the AOSP Android.bp files say, made because we target GNU/Linux on
# host clang rather than Android/bionic. See project_scope.md sections 5 and 6.1.
#
# RULE: every entry carries a comment explaining the Android-vs-Linux reason.
# A submodule bump re-runs Layer 1 (refreshing source lists/deps automatically);
# this file should rarely need to change.
#
# Loaded by bp2cmake.overlay.load_overlay -> must define OVERLAY: Overlay.

OVERLAY = Overlay(
    global_policy=GlobalPolicy(
        # AOSP names map to short CMake target names, matching the archive's
        # hand-written cmake (libbase -> base, liblog -> log, ...). Anything not
        # listed strips a leading "lib".
        name_map={
            "libbase": "base",
            "liblog": "log",
            "libz": "z",          # NOTE: maps to the host system zlib, not an
                                  # in-tree target (audit 5.2 item 6).
            "liblz4": "lz4",      # host system liblz4 (no submodule in archive;
                                  # runtime/dex2oat link it -- needs liblz4-dev).
            "liblzma": "lzma",
            "libnativehelper": "nativehelper",
            "libexpat": "expat",  # host system expat (no submodule)
        },
        # Host/system libs provided as imported targets, not built from AOSP
        # source. The dependency-closure walk skips these (audit 5.2 item 6).
        host_libs=["libz", "liblz4", "libcap", "libexpat"],
        # Dropped from every target: host clang + glibc headers emit warnings the
        # Android toolchain never sees, so -Werror would break the build (audit
        # 5.2 item 8 / 5.4). -Wthread-safety is likewise noisier off-Android.
        # -Wmissing-noreturn (from art_defaults target.linux) also over-fires.
        # -fvisibility=protected (art_defaults, build/Android.bp): AOSP combines
        # the ART runtime+compiler into fewer/larger libs where protected (no
        # cross-module preemption) is an intra-lib optimization. We split ART into
        # MANY shared libs (libart, libartbase, libdexfile, libart-compiler, ...),
        # and A16 made libart an aggregator of libart-runtime+libart-compiler whose
        # symbols other .so's (art-compiler, dex2oat) must reference across the .so
        # boundary. Protected visibility makes those refs un-linkable
        # ("R_X86_64_PC32 against protected symbol ... making a shared object").
        # Drop it -> default visibility, fully exportable. (audit 5.2 item 2/8.)
        drop_cflags=["-Werror", "-Wthread-safety", "-Wmissing-noreturn",
                     "-fvisibility=protected"],
        # ldflags dropped everywhere: --exclude-libs=libziparchive.a is an APEX
        # ODR workaround for static ziparchive (we link it shared); the
        # $ORIGIN/../art_common/... rpath + new-dtags are AOSP host-test layout
        # (audit 5.2 / art_defaults target.linux, libnativeloader notes).
        drop_ldflags=["-Wl,--exclude-libs=libziparchive.a"],
        drop_ldflags_containing=["art_common/out", "--enable-new-dtags"],
        # art.go load-hook cflags, injected into every ART-tree module. These are
        # in NO .bp; many art headers (instruction_set.h stack-overflow gaps,
        # globals.h page-size-agnostic) #error / change ABI without them. Mirror
        # art.go defaults at android-16.0.0_r4 (gaps=8192, host frame=1744,
        # PAGE_SIZE_AGNOSTIC=1) + the Linux target mode.
        #   A16 drift vs the old android-u-beta-4 pin:
        #   - host ART_FRAME_SIZE_LIMIT 1736 -> 1744 (art.go hostFlags).
        #   - +ART_PAGE_SIZE_AGNOSTIC=1: now set UNCONDITIONALLY by art.go
        #     (globals.h/mem_map.h: makes gPageSize a runtime sysconf value and
        #     adds MemMap::page_size_ -- ABI-affecting, so it must be uniform
        #     across every ART TU; this channel applies it to all art/ modules).
        #   - dropped ART_DEFAULT_COMPACT_DEX_LEVEL: CompactDex was removed in
        #     A16 (compact_dex_level.h gone), so the macro is dead.
        art_defines=[
            "ART_STACK_OVERFLOW_GAP_arm=8192",
            "ART_STACK_OVERFLOW_GAP_arm64=8192",
            "ART_STACK_OVERFLOW_GAP_riscv64=8192",
            "ART_STACK_OVERFLOW_GAP_x86=8192",
            "ART_STACK_OVERFLOW_GAP_x86_64=8192",
            "ART_FRAME_SIZE_LIMIT=1744",
            "ART_PAGE_SIZE_AGNOSTIC=1",
            # GC type: art.go sets -DART_DEFAULT_GC_TYPE_IS_<type> on EVERY art
            # module (globalFlags), and A16's compiler now includes runtime/gc/
            # collector_type.h (which #errors without it). Inject tree-wide here,
            # forcing CMS (audit 5.2 item 7): the art.go default is now CMC, which
            # needs userfaultfd (read_barrier_config.h sets gUseUserfaultfd=true
            # under CMC); CMS keeps it false -- correct for a generic host.
            "ART_DEFAULT_GC_TYPE_IS_CMS",
        ],
        strip_lib_prefix=True,
    ),
    modules={
        # --- libbase ---------------------------------------------------------
        # AOSP: cc_library (builds both shared+static), whole_static_libs fmtlib.
        # We build a single shared `base`, inlining fmtlib's format.cc (the
        # archive did exactly this). errors_unix.cpp already comes from Layer 1's
        # target.linux resolution -- that FIXES the archive cmake bug where it
        # was dropped (audit 5.4), so we do NOT need to add it here.
        "libbase": ModulePolicy(
            kind="shared",                # cc_library is ambiguous; pick shared.
            absorb_whole_static=True,     # fmtlib -> compile src/format.cc in.
            # _FILE_OFFSET_BITS=64 is android-only in the .bp, but we want 64-bit
            # off_t on glibc too (large-file correctness). Re-adding it on Linux
            # is a deliberate Layer 2 decision (audit 5.2 item 6 / libbase notes).
            add_defines=["_FILE_OFFSET_BITS=64"],
            # Suppress a host-glibc deprecation noise the archive also silenced.
            add_cppflags=["-Wno-deprecated-declarations"],
        ),

        # --- liblog ----------------------------------------------------------
        # AOSP: cc_library. Layer 1 already drops the target.android logd/pmsg
        # transport sources (logd_reader/writer, pmsg_*). Two MORE sources that
        # survive Layer 1 still need Android libcutils/libutils headers we do not
        # have on Linux: logprint.cpp (cutils/list.h) and event_tag_map.cpp
        # (utils/FastStrcmp.h). Dropping them reduces liblog to the write path,
        # exactly what the archive did (audit 5.2 item 4 / liblog notes). libbase
        # only needs the write/properties path, so this is safe.
        "liblog": ModulePolicy(
            kind="shared",
            remove_srcs=["logprint.cpp", "event_tag_map.cpp"],
            # liblog has no real deps on Linux (Android pulls libcutils_headers
            # only for the dropped sources); nothing to link.
        ),

        # --- libnativehelper -------------------------------------------------
        # AOSP: cc_library_shared, links liblog. The .bp sets -std=c11, but on
        # glibc strict c11 hides strerror_r's declaration (it lives behind
        # _GNU_SOURCE / __USE_GNU). Soong's bionic toolchain effectively builds
        # in gnu mode, so this never bit on Android. On Linux we force gnu11 so
        # JNIHelp.c's strerror_r call is declared. Deliberate port decision.
        "libnativehelper": ModulePolicy(
            kind="shared",
            set_c_std="gnu11",
        ),

        # --- libprocinfo -----------------------------------------------------
        # AOSP: cc_library. Single source, depends on libbase. -fPIC is implicit
        # for Soong shared libs; CMake adds it for SHARED targets automatically.
        "libprocinfo": ModulePolicy(
            kind="shared",
        ),

        # --- libziparchive ---------------------------------------------------
        # AOSP: cc_library. libz maps to the host system zlib (name_map). The
        # incfs support is compiled out via -DINCFS_SUPPORT_DISABLED=1 (already
        # in the .bp cflags), so incfs_support sources stay excluded. cpp_std
        # c++2a flows through automatically.
        # zip_writer.h includes <gtest/gtest_prod.h> for FRIEND_TEST; we have no
        # googletest, so point at the project-owned compat shim (//compat).
        "libziparchive": ModulePolicy(
            kind="shared",
            add_compat_include_dirs=["."],  # compat root provides gtest/gtest_prod.h
        ),

        # --- libtinyxml2 -----------------------------------------------------
        # AOSP: cc_library. The .bp adds -DDEBUG -DANDROID_NDK only under
        # target.android (to route logging to logcat); on Linux we do NOT want
        # that path, so we add nothing (this deliberately DIVERGES from the
        # archive's buggy cmake, which force-enabled those macros on Linux while
        # not even linking liblog -- audit 5.4). tinyxml2 then has no liblog dep.
        "libtinyxml2": ModulePolicy(
            kind="shared",
            remove_shared_libs=["liblog"],  # only needed for the android logcat path
        ),

        # --- liblzma ---------------------------------------------------------
        # AOSP: cc_library, pure C (the 7zip/p7zip backend). Build shared. No
        # CXX_STANDARD games (the archive set C++20 on this pure-C target by
        # mistake -- audit 5.4; we simply don't).
        "liblzma": ModulePolicy(
            kind="shared",
        ),

        # --- libcpu_features -------------------------------------------------
        # AOSP splits this into 3 modules (utils, hwcaps, core) wired by
        # whole_static_libs. We absorb the whole_static deps' sources into one
        # STATIC `cpu_features` (the archive did this). HAVE_STRONG_GETAUXVAL and
        # HAVE_DLFCN_H are bionic-only (target.bionic) in the .bp; on glibc
        # getauxval() exists since 2.16 and dlfcn.h is present, so we force them
        # on -- a deliberate bionic->glibc capability assertion (audit 5.2 item 5
        # / 6). x86_64 does not need the arm-only hwcaps module.
        "libcpu_features": ModulePolicy(
            kind="static",
            absorb_whole_static=True,
            add_defines=["HAVE_STRONG_GETAUXVAL", "HAVE_DLFCN_H"],
        ),

        # === ART core (in progress) =========================================
        # ART modules inherit art_defaults (a normal cc_defaults in
        # art/build/Android.bp), so Layer 1 already picks up its cflag set. What
        # is NOT in any .bp -- and so must live here -- are the art.go-injected
        # build knobs (ART_TARGET[_LINUX], GC type, codegen defines, base
        # addresses). Those go on runtime/dalvikvm when we reach them.

        # --- libartpalette ---------------------------------------------------
        # AOSP: art_cc_library that on Android dlopen()s libartpalette-system;
        # on host it compiles system/palette_fake.cc (Layer 1's target.host /
        # not-android resolution already selects the fake). We just build the
        # shared lib and link base + log. The version_script / dlopen loader are
        # dropped (no APEX on Linux -- audit 5.2 item 4 / libartpalette notes).
        # This is the one ART leaf with NO generated sources, so it is the first
        # ART module we validate.
        "libartpalette": ModulePolicy(
            kind="shared",
            add_shared_libs=["libbase", "liblog"],  # .bp host_linux deps
        ),

        # --- libartbase ------------------------------------------------------
        # AOSP: art_cc_library (shared + static flavors). We build shared
        # `artbase`. The headline issue is art.go-INJECTED defines that appear in
        # NO .bp (audit 5.1): instruction_set.h fails to compile without the
        # stack-overflow-gap and frame-size-limit macros. art.go sets the gaps to
        # 8192 for every arch (art.go:103-108) and ART_FRAME_SIZE_LIMIT=1736 for
        # host non-ASAN (art.go hostFlags, 1744 at android-16.0.0_r4). We assert
        # them here -- the canonical example of Layer 2 owning the Go knobs.
        # libtinyxml2 is whole_static in
        # the .bp; we absorb it (single shared artbase). libz -> host zlib;
        # libcap is a host dev dependency (provided by the harness/toolchain).
        "libartbase": ModulePolicy(
            kind="shared",
            absorb_whole_static=True,   # fold libtinyxml2 in (as the archive did)
            # android-16 libartbase (linux target) links the aconfig flag
            # libraries (art-aconfig-flags-lib, art-aconfig-rw-flags-lib,
            # libaconfig_storage_read_api_cc, libcore-aconfig-flags-native-lib).
            # On Android these are aconfig-generated static libs; we generate the
            # flag headers as header-only inline accessors (bp2cmake/aconfig.py,
            # all flags at default), so the libs are neither built nor needed.
            # Drop the link edges (the headers come via the gensrc include dir).
            remove_static_libs=[
                "art-aconfig-flags-lib",
                "art-aconfig-rw-flags-lib",
                "libaconfig_storage_read_api_cc",
                "libcore-aconfig-flags-native-lib",
            ],
            # PUBLIC so consumers that include instruction_set.h (libdexfile,
            # runtime) see them too -- they propagate via target_link_libraries.
            add_public_defines=[
                "ART_STACK_OVERFLOW_GAP_arm=8192",
                "ART_STACK_OVERFLOW_GAP_arm64=8192",
                "ART_STACK_OVERFLOW_GAP_riscv64=8192",
                "ART_STACK_OVERFLOW_GAP_x86=8192",
                "ART_STACK_OVERFLOW_GAP_x86_64=8192",
                "ART_FRAME_SIZE_LIMIT=1744",
            ],
        ),

        # --- libdexfile ------------------------------------------------------
        # AOSP: art_cc_library (shared + static). We build shared `dexfile`. Uses
        # the operator_out gensrcs pipeline (dexfile_operator_srcs) and depends
        # on artbase -- so it exercises PUBLIC-define propagation: the stack-gap/
        # frame-limit macros reach dexfile through its link to artbase, without
        # being restated here. We absorb external/dex_file_supp.cc (from AOSP's
        # separate libdexfile_support shim) so the art_api::dex::g_ADexFile_*
        # symbols are defined here -- libunwindstack needs them and we dropped
        # libdexfile_support (audit 5.2 item 9 / Part 1).
        "libdexfile": ModulePolicy(
            kind="shared",
            add_srcs=["external/dex_file_supp.cc"],
        ),

        # --- libelffile ------------------------------------------------------
        # AOSP: art_cc_library_static -> the emitter maps that to STATIC
        # automatically (no kind override needed). Depends on base/lzma/artbase.
        # Needs -fPIC since it gets linked into shared libs (Soong implicit;
        # CMake POSITION_INDEPENDENT_CODE handles it for STATIC consumed by
        # SHARED, but we add it explicitly to match the archive).
        "libelffile": ModulePolicy(
            add_cflags=["-fPIC"],
        ),

        # --- libprofile ------------------------------------------------------
        # AOSP: art_cc_library. Shared `profile`; depends on artbase + dexfile
        # (which carry the art.go defines transitively via PUBLIC propagation).
        "libprofile": ModulePolicy(
            kind="shared",
        ),

        # === ART runtime leaf dependencies ==================================

        # --- libsigchain -----------------------------------------------------
        # AOSP: cc_library. Single source (sigchain.cc; Layer 1 picks the linux
        # branch). The -Wl,-z,global ldflag (required so sigchain's signal
        # interposition symbols land in the global scope) already comes from the
        # .bp via Layer 1 -- no overlay add needed (the de-dup keeps it once).
        "libsigchain": ModulePolicy(
            kind="shared",
            # sigchain.cc uses CHAR_BIT without including <climits>; the archive
            # defined it directly (audit / sigchainlib notes). 8 on all targets.
            add_defines=["CHAR_BIT=8"],
        ),

        # --- libnativebridge -------------------------------------------------
        # AOSP: art_cc_library. On Android it links libdl_android + uses
        # dlext_namespaces.h; Layer 1's not-android resolution already dropped
        # those, leaving native_bridge.cc on plain dlopen (audit 5.2 item 3).
        "libnativebridge": ModulePolicy(
            kind="shared",
        ),

        # --- libnativeloader -------------------------------------------------
        # AOSP: art_cc_library. The entire Android namespace engine
        # (library_namespaces.cpp, public_libraries.cpp, libdl_android,
        # libPlatformProperties) is target.android-only -> dropped by Layer 1,
        # leaving native_loader.cpp on bare dlopen (audit 5.2 item 3). nativehelper
        # is header-only here.
        "libnativeloader": ModulePolicy(
            kind="shared",
        ),

        # --- libodrstatslog --------------------------------------------------
        # AOSP: cc_library_static -> STATIC automatically. Layer 1 picked the
        # host source (odr_statslog_host.cc, a no-op stub vs the statsd one).
        # Links artbase. Needs -fPIC (linked into the shared runtime).
        "libodrstatslog": ModulePolicy(
            add_cflags=["-fPIC"],
        ),

        # --- libunwindstack --------------------------------------------------
        # AOSP: cc_library with a big static ecosystem. We build shared
        # `unwindstack`. Two deps don't exist on Linux / in-tree: drop
        # librustc_demangle_static (Rust symbol demangling; not vendored) and
        # swap libdexfile_support (the dlopen shim) for the real dexfile lib --
        # exactly what the archive did (audit Part 1). C++20 (the .bp sets it).
        "libunwindstack": ModulePolicy(
            kind="shared",
            set_cpp_std="gnu++20",
            remove_static_libs=["libdexfile_support", "librustc_demangle_static"],
            add_shared_libs=["libdexfile"],  # real dexfile instead of the shim
        ),

        # === libart — the runtime ===========================================
        # AOSP: art_cc_library (libart.so). 237 srcs (incl. all-arch
        # instruction_set_features + the x86_64 impl) + generated sources:
        #   - art_operator_srcs  (operator_out gensrcs, handled by the emitter)
        #   - cpp-define-generator-asm-support (asm_defines.h, GENERATED by the
        #     Python codegen driver -- bp2cmake/codegen.py -- not the emitter)
        #   - mterp_<arch>.S (also from the codegen driver)
        # The art.go-injected behavioral knobs live here (audit 5.2 item 1/2/7):
        # ART_TARGET + ART_TARGET_LINUX (compile in the "Linux-flavored target"
        # mode), ART_DEFAULT_GC_TYPE_IS_CMS (swap from the CMC default), base
        # addresses, USE_D8_DESUGAR. These MUST match codegen.py's
        # asm_defines_macros (the asm_defines.h is generated with them).
        # Android-only deps (libstatssocket, libdl_android, heapprofd,
        # libstatslog_art, libodrstatslog-on-device) are target.android -> already
        # dropped by Layer 1. libz/liblz4 map to host libs.
        "libart": ModulePolicy(
            kind="shared",
            # A16 libart compiles arch/arm/instruction_set_features_arm.cc which
            # includes <cpu_features_macros.h>. libart depends on libcpu_features
            # (runtime/Android.bp), but cpu_features is whole_static-absorbed into
            # libartbase so its export include doesn't propagate here. Add the
            # cpu_features include dir explicitly (archive external/cpu_features).
            add_include_dirs=["external/cpu_features/include"],
            # PUBLIC: consumers (openjdkjvm, dalvikvm via headers) see GC type etc.
            add_public_defines=[
                "ART_DEFAULT_GC_TYPE_IS_CMS",
                "USE_D8_DESUGAR=1",
                "ART_TARGET",
                "ART_TARGET_LINUX",
            ],
            add_defines=[
                "ART_BASE_ADDRESS=0x60000000",
                "ART_BASE_ADDRESS_MIN_DELTA=(-0x1000000)",
                "ART_BASE_ADDRESS_MAX_DELTA=0x1000000",
                # art.go stack-gap / frame-limit knobs (also on artbase, but
                # libart includes headers needing them directly).
                "ART_STACK_OVERFLOW_GAP_arm=8192",
                "ART_STACK_OVERFLOW_GAP_arm64=8192",
                "ART_STACK_OVERFLOW_GAP_riscv64=8192",
                "ART_STACK_OVERFLOW_GAP_x86=8192",
                "ART_STACK_OVERFLOW_GAP_x86_64=8192",
                "ART_FRAME_SIZE_LIMIT=1744",
            ],
            absorb_whole_static=True,   # libcpu_features whole_static -> inline
            # asm_defines.h (generated_headers: cpp-define-generator-asm-support)
            # and the mterp interpreter assembly come from the Python codegen
            # driver, staged under ${MDVM_GENSRC_DIR}. The emitter handles
            # art_operator_srcs (operator_out gensrcs) itself.
            add_gensrc_includes=["art/asm/include"],         # asm_defines.h
            add_gensrc_sources=["art/asm/mterp/mterp_x86_64.S"],
        ),

        # === javacorenatives (libcore JNI + ICU + crypto) ==================
        # The VM mandatorily dlopens libicu_jni, libjavacore, libopenjdk at
        # startup (runtime.cc:2193-2213, LOG(FATAL) if missing). These + their
        # shared-lib closure must be built. Port decisions mirror the archive's
        # native/cmake/javacorenatives/*.cmake.

        # --- ICU: libicuuc / libicui18n (the C++ ICU impl) -------------------
        # cc_library with srcs:["*.cpp"] (glob-expanded by the converter). Build
        # shared. U_COMMON_IMPLEMENTATION / U_I18N_IMPLEMENTATION mark the impl
        # side; PIC/_REENTRANT for the shared lib; rtti on (ICU needs it).
        "libicuuc": ModulePolicy(
            kind="shared",
            add_defines=["U_COMMON_IMPLEMENTATION", "PIC", "_REENTRANT"],
            add_cflags=["-fPIC", "-fvisibility=hidden", "-frtti",
                        "-Wno-unused-parameter", "-Wno-deprecated-declarations"],
        ),
        "libicui18n": ModulePolicy(
            kind="shared",
            add_defines=["U_I18N_IMPLEMENTATION", "PIC", "_REENTRANT"],
            add_cflags=["-fPIC", "-fvisibility=hidden", "-frtti",
                        "-Wno-unused-parameter", "-Wno-deprecated-declarations"],
        ),
        # ICU stubdata: the .dat is loaded at runtime via ICU_DATA; this lib is
        # the small stub data table. STATIC, absorbed into icuuc.
        "libicuuc_stubdata": ModulePolicy(
            kind="static",
            add_cflags=["-fPIC"],
        ),
        # libandroidicuinit: registers ICU data via udata_setCommonData. STATIC.
        "libandroidicuinit": ModulePolicy(
            kind="static",
            add_cflags=["-fPIC"],
        ),
        # libicu_jni: the JNI bridge libcore/libopenjdk call into. shared.
        "libicu_jni": ModulePolicy(
            kind="shared",
            add_defines=["U_USING_ICU_NAMESPACE=0", "ANDROID_LINK_SHARED_ICU4C",
                         "__INTRODUCED_IN(x)="],
            add_cflags=["-fvisibility=protected", "-Wno-unused-parameter"],
        ),
        # libicu: the stable NDK-style shim re-exporting ICU. AOSP cc_library_static
        # named libicu_static; archive built it SHARED as `icu`. absorb the static.
        "libicu": ModulePolicy(
            kind="shared",
            absorb_whole_static=True,
            add_defines=["U_SHOW_CPLUSPLUS_API=0", "__INTRODUCED_IN(x)="],
            add_cflags=["-fvisibility=protected"],
        ),

        # --- boringssl libcrypto_static (A16 libcore links THIS, not libcrypto)
        # android-16 libcore/NativeCode.bp links libcrypto_static ("for bignums
        # only", non-FIPS) instead of the shared libcrypto. Its .bp defaults
        # already pull libcrypto_bcm_sources (bcm.c) + the fipsmodule asm, so no
        # source injection is needed here (unlike the shared libcrypto entry
        # below, now unused). But it is a cc_library_static linked into the SHARED
        # libjavacore.so / libopenjdk.so, so its objects must be PIC -- otherwise
        # ld fails: "relocation R_X86_64_PC32 against AES_decrypt can not be used
        # when making a shared object; recompile with -fPIC". Force -fPIC.
        "libcrypto_static": ModulePolicy(
            kind="static",
            add_public_defines=["BORINGSSL_IMPLEMENTATION"],
            add_defines=["BORINGSSL_ANDROID_SYSTEM", "OPENSSL_SMALL"],
            add_cflags=["-fPIC", "-fvisibility=hidden", "-Wno-unused-parameter",
                        "-Wno-deprecated-declarations"],
        ),

        # --- boringssl libcrypto (non-FIPS shared) ---------------------------
        # The Android libcrypto pulls its actual crypto core from srcs:
        # [":bcm_object"] -- a cc_object that compiles libcrypto_bcm_sources
        # (bcm.c) with FIPS hash injection (inject_bssl_hash) and a linker
        # script (fips_shared.lds), both `target: android:`-only. The converter
        # can't follow that cc_object module-ref source, so without help
        # libcrypto.so ships with ONLY the libcrypto_sources wrappers and none
        # of the BIGNUM/EC/RSA/SHA/AES/cipher implementations -- 320 undefined
        # symbols. That stays hidden while libcrypto is only ever a .so (shared
        # libs tolerate undefined symbols) and first bites when dex2oat does a
        # hard executable link against it.
        #
        # The FIPS machinery (self-integrity hash, single text/data section,
        # linker script) is genuinely Android-only and we drop it -- but bcm.c
        # itself is the crypto core, NOT FIPS attestation: it is a unity file
        # that #includes 76 .c primitives. So we inject bcm.c + the x86_64
        # fipsmodule asm as plain sources, exactly as the archive's hand-port
        # libcrypto.cmake did (it lists bcm.c first, then linux-x86_64/.../
        # fipsmodule/*.S). x86_64-only to match the fixed host Config. Defines
        # per archive libcrypto.cmake; OPENSSL_SMALL keeps it lean.
        "libcrypto": ModulePolicy(
            kind="shared",
            add_public_defines=["BORINGSSL_IMPLEMENTATION"],
            add_defines=["BORINGSSL_SHARED_LIBRARY", "BORINGSSL_ANDROID_SYSTEM",
                         "OPENSSL_SMALL"],
            add_cflags=["-fPIC", "-fvisibility=hidden", "-Wno-unused-parameter",
                        "-Wno-deprecated-declarations"],
            add_srcs=[
                "src/crypto/fipsmodule/bcm.c",
                "linux-x86_64/crypto/fipsmodule/aesni-gcm-x86_64-linux.S",
                "linux-x86_64/crypto/fipsmodule/aesni-x86_64-linux.S",
                "linux-x86_64/crypto/fipsmodule/ghash-ssse3-x86_64-linux.S",
                "linux-x86_64/crypto/fipsmodule/ghash-x86_64-linux.S",
                "linux-x86_64/crypto/fipsmodule/md5-x86_64-linux.S",
                "linux-x86_64/crypto/fipsmodule/p256-x86_64-asm-linux.S",
                "linux-x86_64/crypto/fipsmodule/p256_beeu-x86_64-asm-linux.S",
                "linux-x86_64/crypto/fipsmodule/rdrand-x86_64-linux.S",
                "linux-x86_64/crypto/fipsmodule/rsaz-avx2-linux.S",
                "linux-x86_64/crypto/fipsmodule/sha1-x86_64-linux.S",
                "linux-x86_64/crypto/fipsmodule/sha256-x86_64-linux.S",
                "linux-x86_64/crypto/fipsmodule/sha512-x86_64-linux.S",
                "linux-x86_64/crypto/fipsmodule/vpaes-x86_64-linux.S",
                "linux-x86_64/crypto/fipsmodule/x86_64-mont-linux.S",
                "linux-x86_64/crypto/fipsmodule/x86_64-mont5-linux.S",
            ],
        ),

        # --- fdlibm (libfdlibm) ----------------------------------------------
        # AOSP cc_library_static -> STATIC. Little-endian host. -fPIC to link
        # into shared libopenjdk.
        "libfdlibm": ModulePolicy(
            add_defines=["_IEEE_LIBM", "__LITTLE_ENDIAN"],
            add_cflags=["-fPIC"],
        ),

        # --- libandroidio ----------------------------------------------------
        # AOSP shared lib (Android I/O shim). On Linux just build it shared.
        "libandroidio": ModulePolicy(
            kind="shared",
        ),

        # --- libjavacore (the libcore JNI core) ------------------------------
        # srcs come from :luni_native_srcs filegroup (converter expands it).
        # Force the glibc host macros (Sigh.) the archive set, and the ICU ns.
        # libexpat is a host system lib (no submodule); name-mapped + host_libs.
        # libnativehelper_compat_libc++ has no Linux equivalent -> dropped.
        "libjavacore": ModulePolicy(
            kind="shared",
            add_defines=["U_USING_ICU_NAMESPACE=0", "__GLIBC__",
                         "_LARGEFILE64_SOURCE", "_GNU_SOURCE", "LINUX",
                         "__INTRODUCED_IN(x)=", "LIBICU_U_SHOW_CPLUSPLUS_API=1"],
            add_cflags=["-fvisibility=protected", "-Wno-unused-parameter",
                        "-Wno-unused-variable", "-Wno-parentheses-equality",
                        "-Wno-constant-logical-operand", "-Wno-sometimes-uninitialized"],
            add_include_dirs=["external/boringssl/src/include"],  # openssl/*.h
            remove_static_libs=["libnativehelper_compat_libc++"],
        ),

        # --- libopenjdk (OpenJDK natives) ------------------------------------
        # Depends on libopenjdkjvm + javacore + fdlibm. Same glibc macros.
        "libopenjdk": ModulePolicy(
            kind="shared",
            add_defines=["U_USING_ICU_NAMESPACE=0", "__GLIBC__",
                         "_LARGEFILE64_SOURCE", "_GNU_SOURCE", "LINUX",
                         "__INTRODUCED_IN(x)="],
            add_cflags=["-fvisibility=protected", "-Wno-unused-parameter"],
            # openssl/*.h for System.c; fdlibm.h for StrictMath.c (the source
            # uses a ../../external/fdlibm relative include, so add that base).
            add_include_dirs=["external/boringssl/src/include"],
            remove_static_libs=["libnativehelper_compat_libc++"],
        ),

        # --- libopenjdkjvm (JVMTI-ish shim into libart) ----------------------
        "libopenjdkjvm": ModulePolicy(
            kind="shared",
        ),

        # --- dalvikvm (the executable) ---------------------------------------
        # -Wl,--export-dynamic so JNI/plugin .so's can resolve back into the exe
        # (audit dalvikvm notes). -pie is added (Soong implicit for executables;
        # CMake is not). Links the runtime + nativehelper + sigchain (the .bp
        # host variant whole_static_libs libsigchain and gets libart via deps;
        # we link them explicitly). NOTE: the final link is blocked until libart
        # fully compiles (the art_method-inl.h FillVRegs source issue) -- this
        # entry validates the executable conversion path meanwhile.
        "dalvikvm": ModulePolicy(
            kind="executable",
            absorb_whole_static=False,   # link libsigchain as a lib, don't inline
            add_cflags=["-fPIC"],
            add_ldflags=["-pie"],
            add_shared_libs=["libart", "libsigchain"],
        ),

        # === dex2oat (the AOT compiler, for building a boot image) ==========
        # AOSP links dex2oat against a big static aggregation (libdex2oat_static
        # -> *_static_defaults + libvixl + arm codegen). We instead link the
        # SHARED libs we already build (matches our whole-project approach) and
        # drop the arm-only libvixl (x86_64 codegen doesn't need it).
        "libart-disassembler": ModulePolicy(
            kind="shared",
        ),
        "libart-compiler": ModulePolicy(
            kind="shared",
            # A16: libart-compiler is a static lib meant to be combined WITH
            # libart-runtime inside libart.so. As a STANDALONE shared lib (for
            # dex2oat) it needs the runtime symbols, so link libart explicitly
            # (in beta-4 the compiler implicitly had them). Also the disassembler.
            add_shared_libs=["libart", "libart-disassembler"],
        ),
        # (libart-dexlayout REMOVED in A16: the dexlayout/ directory is gone, so
        # there is no libart-dexlayout module/target. Nothing links it now.)
        "libart-dex2oat": ModulePolicy(
            kind="shared",
            add_shared_libs=["libart-compiler"],
        ),
        "dex2oat": ModulePolicy(
            kind="executable",
            absorb_whole_static=False,
            add_cflags=["-fPIC"],
            add_ldflags=["-pie"],
            remove_static_libs=["libdex2oat_static"],
            add_shared_libs=["libart-dex2oat", "libart-compiler",
                             "libart", "libartbase",
                             "libdexfile", "libprofile", "libartpalette",
                             "libelffile"],
        ),
    },
)
