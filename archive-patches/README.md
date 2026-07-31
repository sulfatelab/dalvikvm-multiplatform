# Archived port notes

This directory is historical and diagnostic documentation. It is not an active
patch queue, and none of its files should be applied mechanically to the current
tree. Current vendor changes are committed on the nested `artmp_*` branches and
the top-level repository records their Git commit IDs.

Audit date: 2026-07-31

## Current disposition

| Note | Current state | Reuse value | Disposition |
|---|---|---|---|
| `0001` FillVRegs ambiguity (below) | Obsolete in Android 16; upstream replaced the ambiguous terminal overload | Only for rebuilding the old 2023 `MinDalvikVM-Archive` with Clang 17 or newer | Keep this explanation; never apply it to current ART |
| Phase 0 zip/logging type fixes (below) | Applied in nested `vendor/libziparchive` commit `a710e1e4` and `vendor/logging` commit `c29f3eeaa` | The C/C++ interoperability rationale remains platform-independent | Keep as legacy-build context |
| Phase 0 ART `ZeroMemory` and 64-bit file-offset fixes | Applied in nested ART commit `90e063dfcd` | Required by every Windows architecture; the offset width is an API/property issue, not a CPU issue | Current nested ART is authoritative |
| `windows_x64_phase2_interpreter_jni.md` | Rejected and removed; ART commit `42a03f2ea0` restored the upstream interpreter policy | Useful as an explicit anti-pattern for future Windows architectures | Keep the short tombstone; do not restore the signature table |
| `windows_x64_phase3_classpath_separator.md` | Applied in ART commit `90e063dfcd` | Required by every Windows architecture and ABI | Keep as design rationale |
| `windows_x64_phase3_dns_localhost_hang.md` | Applied to the Phase 3 probes | Reusable test-harness rule on Windows and Linux | Keep as test rationale |
| `windows_x64_phase3_java_version_version_class.md` | Applied; the shared boot-jar build now selects the `JAVA_VERSION = "1.8.0"` source before compiling `Version` | Reusable whenever a compile-time constant source is overlaid | Keep as boot-library rationale |
| `windows_x64_phase3_memmap_low4g_virtualquery.md` | Superseded by ART commit `2fa301a13b`, which uses Windows 10 `VirtualAlloc2` address requirements | The old `VirtualQuery` scan is only a legacy fallback for a pre-Windows-10 design, which this project does not support | Keep as historical diagnosis; do not reapply |
| `windows_x64_phase3_poll_select_win10.md` | Applied in `tools/windows_x64/jni_stubs/win_net_natives.c` | Required by all supported Windows architectures when CRT descriptors wrap Winsock sockets | Keep as Windows socket rationale |
| `windows_x64_phase3_runtime_memory.md` | Applied in nested ART plus the project-owned Runtime JNI bridge | Reusable for every Windows architecture until the full upstream OpenJDK JVM layer is portable | Keep as module-boundary rationale |
| `windows_x64_phase3_system_gc_hang_fix.md` | Applied in ART commit `90e063dfcd` | The Windows timing and wait semantics are architecture-neutral | Keep the diagnosis; current ART source is authoritative |
| Full `time_utils.cc` and `mutex-inl.h` snapshots | Byte-for-byte identical to current nested ART files at this audit | None beyond the current source and nested Git history | Removed as redundant copies |

The `windows_x64` names record the phase in which each issue was discovered.
Unless a note says otherwise, a Windows OS/API rule applies equally to `x86`,
`x86_64`, `armv7`, `aarch64`, and `arm64ec`; CPU- or ABI-specific applicability
must be established by the unified test catalog before enabling a target.

## Legacy `MinDalvikVM-Archive` patch

The old archive was normally read-only. Its 2023 ART snapshot needed one source
change to compile with Clang 17 or newer. In
`native/art/runtime/art_method-inl.h`, remove the unused value parameters from
the terminal `FillVRegs` overload so it can match only the empty pack:

```diff
 template <char... ArgType>
-inline ALWAYS_INLINE void FillVRegs(uint32_t* vregs ATTRIBUTE_UNUSED,
-                                    typename ShortyTraits<ArgType>::Type... args ATTRIBUTE_UNUSED)
+inline ALWAYS_INLINE void FillVRegs(uint32_t* vregs ATTRIBUTE_UNUSED)
     REQUIRES_SHARED(Locks::mutator_lock_) {}
```

Current Android 16 ART has a single recursive overload guarded by `if constexpr`
and does not contain the ambiguity. This legacy edit is therefore not a candidate
for the current nested ART branch or a future ART version.

## Legacy Phase 0 edits

The Phase 0 archive build also temporarily changed these old-archive files:

- `native/libziparchive/zip_cd_entry_map.h`: both `ZipStringOffset20` bitfields
  use `uint32_t`;
- `native/logging/liblog/include/android/log.h`: `enum log_id` has the fixed
  underlying type `uint32_t`;
- `native/logging/liblog/logger.h`: C++ uses `std::atomic_int` rather than a
  conflicting C `atomic_int` definition.

Equivalent fixes are already committed in the current nested repositories.
They remain documented only for a deliberate rebuild of the old archive.

The Phase 0 ART build also exposed the Windows SDK `ZeroMemory` macro collision
and the Windows CRT's 32-bit `off_t`. The current nested ART branch undefines the
macro around ART's `ZeroMemory` function and uses `off64_t` for `FdReadOffset` on
Windows. Those implementations are committed in `90e063dfcd`; they are not
old-archive reapply instructions.
