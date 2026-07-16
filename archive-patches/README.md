# Patches applied to the read-only archive

The archive (`../MinDalvikVM-Archive`) is normally read-only. The user authorized
exactly ONE source change to make the 2023 ART sources compile under clang-21.
This directory records it so it is not lost (and so it can be re-applied / sent
upstream / dropped after a submodule bump).

When the `art` submodule is updated to current AOSP, check whether this is still
needed (it is fixed upstream) and drop it if so.

## 0001: art_method-inl.h FillVRegs overload ambiguity (clang>=17)

File: `native/art/runtime/art_method-inl.h`

`FillVRegs` had two overloads — a terminal `template<char...> FillVRegs(uint32_t*,
ShortyTraits<ArgType>::Type...)` and a recursive `template<char First, char...>
FillVRegs(uint32_t*, First, ShortyTraits<ArgType>::Type...)`. For a 1+-arg call
both matched with identical/ambiguous signatures, and because
`ShortyTraits<...>::Type` is a non-deduced context, clang>=17 can no longer pick
a more-specialized overload → hard error "call to 'FillVRegs' is ambiguous".

Fix (behavior-preserving): drop the value parameters from the TERMINAL overload
so it only matches the empty pack:

```diff
 template <char... ArgType>
-inline ALWAYS_INLINE void FillVRegs(uint32_t* vregs ATTRIBUTE_UNUSED,
-                                    typename ShortyTraits<ArgType>::Type... args ATTRIBUTE_UNUSED)
+inline ALWAYS_INLINE void FillVRegs(uint32_t* vregs ATTRIBUTE_UNUSED)
     REQUIRES_SHARED(Locks::mutator_lock_) {}
```

The terminal case never used its value args (they were ATTRIBUTE_UNUSED), so the
runtime behavior is identical; it just stops the terminal overload from being a
candidate for non-empty calls. After this, `libart.so` and `dalvikvm` build and
run (ART version 2.1.0 x86_64).

## Win64 Phase 0 (2026-07-16)

Temporary edits under MinDalvikVM-Archive for PE builds (re-apply on clean archive checkout):

- `native/libziparchive/zip_cd_entry_map.h` — `ZipStringOffset20` bitfields both `uint32_t`
- `native/logging/liblog/include/android/log.h` — `enum log_id : uint32_t`
- `native/logging/liblog/logger.h` — C++ `std::atomic_int` instead of C `atomic_int` conflicting with libc++

Vendor art patches (in-tree):

- `vendor/art/libartbase/base/mem_map.h` / `mem_map.cc` — `#undef ZeroMemory` on `_WIN32`
- `vendor/art/libartbase/base/unix_file/fd_file.cc` — `FdReadOffset` = `off64_t` on Windows

## Win64 Phase 3 (2026-07-16)

Vendor tree is gitignored; durable reapply notes:

- `win64_phase3_classpath_separator.md` — classpath / `path.separator` is `;`
- `win64_phase3_memmap_low4g_virtualquery.md` — Windows low-4G MemMap VirtualQuery free-region search for LOS
- `win64_phase3_system_gc_hang_fix.md` — forced `System.gc` hang: ThreadCpuNanoTime + WaitOnAddress timeout
- `win64_phase3_time_utils.cc` / `win64_phase3_mutex-inl.h` — snapshot sources for reapply
- `win64_phase3_runtime_memory.md` — Runtime free/total/maxMemory PE+art JVM_* fix
- `win64_phase3_java_version_version_class.md` — recompile sun.misc.Version for java.version=1.8.0
- `win64_phase3_poll_select_win10.md` — real Win10 poll EINVAL → select()
- `win64_phase3_dns_localhost_hang.md` — DnsProbe hang: localhost ::1 vs 127.0.0.1 + missing SO_TIMEOUT
