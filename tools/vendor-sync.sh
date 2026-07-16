#!/usr/bin/env bash
# dalvikvm-multiplatform helper: seed/refresh nested vendor pins from AOSP tags.
# Prefer artmp_* branches + gitlinks in normal workflow; this script is a bootstrap/repair tool.
# Fetch art + libcore at a coherent AOSP snapshot into vendor/, then apply the
# host-toolchain patches recorded in //vendor-patches/README.md. Reproducible:
# re-run after deleting vendor/art or vendor/libcore. The archive is NEVER used
# for art/libcore once this runs (see native/generate.sh --exclude-top art).
set -euo pipefail
TAG="${MDVM_AOSP_TAG:-android-16.0.0_r4}"
HERE="$(cd "$(dirname "$0")/../vendor" && pwd)"; mkdir -p "$HERE"
BASE="https://android.googlesource.com/platform"

clone() {  # repo
  local r="$1"
  if [ ! -d "$HERE/$r/.git" ]; then
    echo ">> cloning $r @ $TAG"
    git clone --depth 1 --branch "$TAG" "$BASE/$r" "$HERE/$r"
  else
    echo ">> $r already present (skip clone)"
  fi
}

clone art
clone libcore

# AOSP's own r8/d8 prebuilt (the boot-classpath dexer). Needed because modern
# SDK d8 strips core java.* classes and lacks the platform/core-library mode;
# this r8 supports --android-platform-build. Fetch the single jar, matching the
# art/libcore snapshot tag so the dexer and the core library stay coherent.
if [ ! -f "$HERE/r8/r8.jar" ]; then
  echo ">> fetching AOSP prebuilts/r8 r8.jar @ $TAG"
  mkdir -p "$HERE/r8"
  curl -s "https://android.googlesource.com/platform/prebuilts/r8/+/refs/tags/$TAG/r8.jar?format=TEXT" \
    | base64 -d > "$HERE/r8/r8.jar"
fi

# AOSP libnativehelper header-only headers @ the same tag. android-16 art's
# runtime/native/*.cc use nativehelper/utils.h (NEW header) and the updated
# ScopedUtfChars (adds `operator std::string_view()`), neither present in the
# archive's 2023 libnativehelper. We keep building the nativehelper .so from the
# archive (ABI-compatible), but art must COMPILE against the A16 header-only API,
# so vendor just these headers and put them first on art's include path
# (native/CMakeLists.txt). Reproducible: delete vendor/nativehelper-headers to refetch.
NHH="$HERE/nativehelper-headers/nativehelper"
if [ ! -f "$NHH/utils.h" ]; then
  echo ">> fetching AOSP libnativehelper header_only_include @ $TAG"
  mkdir -p "$NHH"
  NHBASE="https://android.googlesource.com/platform/libnativehelper/+/refs/tags/$TAG/header_only_include/nativehelper"
  for h in nativehelper_utils.h scoped_local_frame.h scoped_local_ref.h \
           scoped_primitive_array.h scoped_string_chars.h scoped_utf_chars.h utils.h; do
    curl -s "$NHBASE/$h?format=TEXT" | base64 -d > "$NHH/$h"
  done
fi

echo ">> applying vendor patches (see vendor-patches/README.md)"

# (Former patch 0001 — art_method-inl.h FillVRegs terminal-overload ambiguity —
# became OBSOLETE at android-16.0.0_r4. Upstream rewrote FillVRegs to use a
# single overload with `if constexpr (sizeof...(args) > 0)` recursion (no
# zero-arg terminal overload), so the clang>=17 variadic ambiguity is gone.)

# 0002 class_linker.cc: bare nullptr_t -> std::nullptr_t. (A16: the param gained
# a [[maybe_unused]] attribute -> `Finish([[maybe_unused]] nullptr_t np)`.)
f="$HERE/art/runtime/class_linker.cc"
if grep -qE 'Finish\(\[\[maybe_unused\]\] nullptr_t np' "$f" 2>/dev/null; then
  sed -i 's/Finish(\[\[maybe_unused\]\] nullptr_t np/Finish([[maybe_unused]] std::nullptr_t np/' "$f"
  echo "   patched 0002 nullptr_t"
elif grep -q 'Finish(nullptr_t np' "$f" 2>/dev/null; then
  sed -i 's/Finish(nullptr_t np/Finish(std::nullptr_t np/' "$f"
  echo "   patched 0002 nullptr_t (pre-A16 form)"
fi

# 0003 thread_linux.cc: constexpr kHostAltSigStackSize uses MINSIGSTKSZ, a
# non-const sysconf() call on glibc>=2.34 -> drop constexpr.
f="$HERE/art/runtime/thread_linux.cc"
if grep -q 'static constexpr int kHostAltSigStackSize' "$f" 2>/dev/null; then
  sed -i 's/static constexpr int kHostAltSigStackSize/static const int kHostAltSigStackSize/' "$f"
  echo "   patched 0003 kHostAltSigStackSize"
fi

# 0004 thread.cc: PTHREAD_STACK_MIN is a non-const long on glibc>=2.34; the file
# has `#pragma clang diagnostic error "-Wconversion"`, so the long->size_t
# assignment is a hard error no command-line flag can override. Cast explicitly.
f="$HERE/art/runtime/thread.cc"
if grep -q 'stack_size < PTHREAD_STACK_MIN' "$f" 2>/dev/null; then
  sed -i 's/stack_size < PTHREAD_STACK_MIN/stack_size < static_cast<size_t>(PTHREAD_STACK_MIN)/; s/stack_size = PTHREAD_STACK_MIN;/stack_size = static_cast<size_t>(PTHREAD_STACK_MIN);/' "$f"
  echo "   patched 0004 PTHREAD_STACK_MIN cast"
fi

# 0005 OpenjdkJvm.cc: JVM_IsNaN calls bare isnan(d); <cmath> only provides
# std::isnan, and we can't force <math.h> globally (its glibc-2.40 canonicalize()
# collides with OpenJDK's). Qualify it.
f="$HERE/art/openjdkjvm/OpenjdkJvm.cc"
if grep -q 'return isnan(d);' "$f" 2>/dev/null; then
  sed -i 's/return isnan(d);/return std::isnan(d);/' "$f"
  echo "   patched 0005 JVM_IsNaN std::isnan"
fi

# (Former patch 0006 — String::ClassSize +67 -> +66 — was REMOVED 2026-06-21.
# It had matched a String mislinked to 771 vtable bytes by the uninitialized-
# BitVector bug now fixed in patch 0009. With correct linking, String links at
# the canonical 779 and AOSP's original +67 is right, so forcing +66 instead
# re-breaks CheckSystemClass(String). Leave string-inl.h at upstream +67.)

# (Former patch 0007 — dexlayout/dex_ir.h Iterator::operator- const — became
# OBSOLETE at android-16.0.0_r4: the entire dexlayout/ directory was removed
# upstream (only dexdump/dexlist remain), and dalvikvm does not depend on it.)

# (Former patch 0008 — register_allocator_linear_scan.cc RemoveIntervalAndPotential
# OtherHalf return type — became OBSOLETE at android-16.0.0_r4: upstream
# refactored the function away; the symbol no longer exists in compiler/.)

# 0009 runtime/class_linker.cc: LinkMethodsHelper::AssignVTableIndexes builds a
# BitVector `initialized_methods` over an UNINITIALIZED alloca/arena buffer
# using the preallocated-storage BitVector ctor, which (unlike the allocating
# ctor) does NOT clear the storage. The algorithm assumes the bits start at 0
# (it only SetBit()s and tests). Garbage bits make IsBitSet() spuriously true
# on a super slot's first encounter -> same_signature_vtable_lists[j] is set to
# a freshly-loaded ArtMethod's method_index (0) -> self-loop (list[0]==0) ->
# the vtable walk at the use site spins forever (the guarding DCHECK_LT is
# compiled out under NDEBUG). Latent upstream bug, masked when the page is
# already zero. Zero the buffer explicitly right after construction.
f="$HERE/art/runtime/class_linker.cc"
if grep -q 'BitVector initialized_methods(/\* expandable= \*/ false,' "$f" 2>/dev/null \
   && ! grep -q 'std::fill_n(bit_vector_buffer_ptr, bit_vector_size, 0u);' "$f" 2>/dev/null; then
  python3 - "$f" <<'PY'
import sys, re
p = sys.argv[1]
s = open(p).read()
anchor = ("  BitVector initialized_methods(/* expandable= */ false,\n"
          "                                Allocator::GetNoopAllocator(),\n"
          "                                bit_vector_size,\n"
          "                                bit_vector_buffer_ptr);\n")
add = ("  // MDVM patch 0009: the backing buffer (alloca/arena) is NOT zeroed and this\n"
       "  // BitVector ctor does not clear it; the algorithm relies on zeroed bits.\n"
       "  // Uninitialized bits cause a same_signature_vtable_lists self-loop that\n"
       "  // hangs the vtable walk (guarding DCHECK_LT is gone under NDEBUG).\n"
       "  std::fill_n(bit_vector_buffer_ptr, bit_vector_size, 0u);\n")
assert anchor in s, "anchor not found for patch 0009"
s = s.replace(anchor, anchor + add, 1)
open(p, "w").write(s)
print("   patched 0009 initialized_methods clear")
PY
fi

# (Former patch 0010 — art_method-inl.h InvokeStatic/Instance arg byte count —
# became OBSOLETE at android-16.0.0_r4: upstream now passes
# `vregs.empty() ? nullptr : vregs.data()` with byte count
# `vregs.size() * sizeof(value_type)`, i.e. exactly this fix, natively.)

# 0011 runtime/oat/oat_file_assistant.cc: fmt::streamed() is fmtlib>=8.0, but the
# archive's host fmtlib is v7.1.3 (foundational libs stay archive-pinned). The
# two call sites format an OatStatus / CompilerFilter::Filter, both of which have
# operator<<. Replace fmt::streamed(X) with a v7-safe MdvmStreamed(X) helper that
# stringifies via std::ostringstream (<sstream> already included).
f="$HERE/art/runtime/oat/oat_file_assistant.cc"
if grep -q 'fmt::streamed(' "$f" 2>/dev/null \
   && ! grep -q 'MdvmStreamed' "$f" 2>/dev/null; then
  anchor='namespace art HIDDEN {'
  helper='namespace art HIDDEN {\n\n\/\/ MDVM patch 0011: archive fmtlib is v7 (no fmt::streamed, added in v8). Stringify\n\/\/ a streamable value via operator<< so ART_FORMAT(\"{}\") can take it.\ntemplate <typename T> static inline std::string MdvmStreamed(const T\& v) {\n  std::ostringstream oss; oss << v; return oss.str();\n}'
  sed -i "s/^namespace art HIDDEN {$/$helper/" "$f"
  sed -i 's/fmt::streamed(/MdvmStreamed(/g' "$f"
  echo "   patched 0011 fmt::streamed -> MdvmStreamed"
fi

# 0012 runtime/{native_stack_dump,thread_list,thread}.cc:
# AndroidLocalUnwinder::set_check_global_elf_cache() is a newer libunwindstack
# API absent from the archive's 2023 libunwindstack. It only toggles a global
# ELF cache optimization; dropping the calls is behavior-preserving (the
# unwinder works without the cache). Comment out each call.
for f in "$HERE/art/runtime/native_stack_dump.cc" \
         "$HERE/art/runtime/thread_list.cc" \
         "$HERE/art/runtime/thread.cc"; do
  if grep -q '\.set_check_global_elf_cache(true);' "$f" 2>/dev/null; then
    sed -i 's/\([a-zA-Z_]*\)\.set_check_global_elf_cache(true);/\/* MDVM patch 0012: archive libunwindstack lacks set_check_global_elf_cache *\/ (void)0;/g' "$f"
    echo "   patched 0012 set_check_global_elf_cache ($(basename "$f"))"
  fi
done

# 0013 libartbase/base/macros.h: neutralize HIDDEN/PROTECTED visibility macros.
# A16 wraps the entire `art` namespace in `namespace art HIDDEN { ... }` (HIDDEN
# = __attribute__((visibility("hidden"))) under NDEBUG) across ~1100 files, plus
# LIBART_PROTECTED on some globals. This is fine on Android where ART is ONE
# libart.so with a curated EXPORT set, but this project deliberately splits ART
# into many shared libs (libart, libartbase, libdexfile, libart-compiler,
# dex2oat, ...) that reference each other's internals across the .so boundary.
# Hidden visibility makes those cross-.so references un-linkable (undefined /
# "relocation against hidden symbol ... making a shared object"). Make HIDDEN and
# PROTECTED no-ops (exactly what the macros already do in the !NDEBUG branch) so
# every symbol gets default visibility and is exportable. Keep EXPORT as-is
# (default visibility). Consistent with the port's no-version-script,
# self-contained-.so policy (audit 5.2 item 8).
f="$HERE/art/libartbase/base/macros.h"
if grep -q '#define HIDDEN __attribute__((visibility("hidden")))' "$f" 2>/dev/null; then
  sed -i 's/#define HIDDEN __attribute__((visibility("hidden")))/#define HIDDEN \/* MDVM patch 0013: export-all for the multi-.so host split *\//; s/#define PROTECTED __attribute__((visibility("protected")))/#define PROTECTED/' "$f"
  echo "   patched 0013 HIDDEN/PROTECTED no-op"
fi
# Same rationale for ALWAYS_HIDDEN: it pins gPageSize / PageSize::value_ inside
# libart.so (runtime.cc), but art-compiler.so / dex2oat (separate .so's in our
# split) reference gPageSize across the boundary -> undefined hidden symbol.
# Export it (one definition still lives in libart.so; others link to it).
if grep -q '#define ALWAYS_HIDDEN __attribute__((visibility("hidden")))' "$f" 2>/dev/null; then
  sed -i 's/#define ALWAYS_HIDDEN __attribute__((visibility("hidden")))/#define ALWAYS_HIDDEN \/* MDVM patch 0013 *\//' "$f"
  echo "   patched 0013 ALWAYS_HIDDEN no-op"
fi

# 0014 libartbase/base/inlined_vector.h: size_ was never initialized.
# InlinedVector is used by Class::GetDeclaredFields (and a few other collectors).
# ConcurrentHashMap has 37 fields > kMaxStackEntries(8), so GetArray() used size_.
# Uninitialized size_ made GetArray return a garbage length; CreateFromArtField
# then dereferenced null ArtField* (SIGSEGV at +66 during CHM.<clinit> via
# Unsafe.objectFieldOffset). Adding fprintf "fixed" it by zeroing stack — classic
# Heisenbug. Initialize size_ to 0.
f="$HERE/art/libartbase/base/inlined_vector.h"
if [ -f "$f" ] && ! grep -q 'MDVM patch 0014' "$f" 2>/dev/null; then
  python3 - "$f" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
old = "class InlinedVector {\n public:\n  void push_back(const T& value) {\n"
new = ("class InlinedVector {\n public:\n"
       "  // MDVM patch 0014: size_ must start at 0. The implicit default ctor left it\n"
       "  // uninitialized; with ConcurrentHashMap's 37 fields (>kMaxStackEntries=8)\n"
       "  // GetArray() then returned a huge garbage length and CreateFromArtField saw\n"
       "  // null ArtField* pointers (SIGSEGV at +66). fprintf Heisenbug: stack zeroing.\n"
       "  InlinedVector() : size_(0u) {}\n\n"
       "  void push_back(const T& value) {\n")
assert old in s, "anchor not found for patch 0014"
s = s.replace(old, new, 1)
s = s.replace("  size_t size_;", "  size_t size_ = 0u;", 1)
open(p, "w").write(s)
print("   patched 0014 InlinedVector size_ init")
PY
fi

echo ">> vendor sync done ($TAG)"
