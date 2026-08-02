# Stack high-water result

The JNI DSO records allocation-free Windows stack-overflow high-water data.
Its current selector is `windows` / `x86_64` / `msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| `RelWithDebInfo-win32-stack-high-water` | PASS: switch 6448 B, nterp 7568 B, JIT 7632 B minimum native margins | 2026-08-01 |
| `Debug-win32-stack-high-water` | PASS: switch 70848 B, nterp 37120 B, JIT 37248 B minimum native margins | 2026-08-01 |

The unified catalog owns the Java/JNI sources, shell-free three-mode runner,
log validator, and allocation-free/direct-store structural reviewer. Each mode
emitted four complete main/child records, exited zero, and created no dump.
Both complete W-014 runs passed 9/9; their immediate repeats were Ninja no-ops
and passed 9/9 again.

FS-1 is intentionally available only through the exact test-only variant
`win32-stack-high-water` on `windows-x86_64-msvc`. The frontend gives the
variant a fingerprinted output directory and rejects product staging from it.
The product configuration still builds the managed/JNI artifacts compile-only
without defining `ART_WIN32_STACK_HIGH_WATER`. Its W-014 host review now proves
that the product `art.dll` has no FS-1 export, its generated asm definitions
have no FS-1 offsets, and its GNU-style Clang commands have no instrumentation
definition. The Linux-hosted Windows product and freshly built FS-1 variant
both passed their respective negative/positive reviewers on 2026-08-02; both
immediate repeats were Ninja no-ops. Other target architectures remain
non-applicable.

At main commit `d9e103e`, a fresh Windows Server 2025 build-26100.32230 product
accepted this isolation review in 0.34 seconds and passed the complete catalog
at 77/77. The immediate `art-tests` repeat was a Ninja no-op, accepted the
review again in 0.33 seconds, and passed 77/77. The subsequently completed
product closure included `art-compiler.dll`, repeated as a no-op, and staged
156 regular files with zero reparse points.

The authoritative Windows Server 2025 source projection and both variant
output trees contained zero reparse points. Aggregate JSON stores target IDs,
artifact names and hashes, exits, marker outcomes, mode counts, and validator
identity without absolute host paths.

## Historical FS-1 native acceptance

The original 2026-07-29 Server 2025 build-26100 package had SHA-256
`22195128d460eef6fe260b79f25e792a2af5303546fadacc7ad188038c09bfbe`.
The hash matched before and after transfer, and the package runner verified its
complete internal checksum manifest before starting Release and Debug switch,
nterp, and threshold-zero JIT processes.

The instrumented overflow path used fixed-size thread-owned records and direct
RSP stores at the failing explicit check, quick throw entry/completed frame,
common throw entry, expanded/restored stack boundary, exception construction,
delivery, and long jump. Formatting, arithmetic, and completeness checks ran
only after Java caught `StackOverflowError`; the structural gate proved that
product `art.dll` contained neither the probe export nor its asm offsets.

All six historical native processes emitted four complete main/child records,
passed boundary/reserve/margin arithmetic, and left no dump or ART fatal
VEH/UEF marker:

```text
Release switch=6784 nterp=7536 jit=7616
Debug   switch=69744 nterp=37168 jit=37232
```

Final-source Wine controls passed at Release margins 7536/7520/7616 and Debug
margins 69728/37216/37232 for switch/nterp/JIT respectively.

The first native Debug run instead raised `STATUS_STACK_OVERFLOW` while
constructing `StackOverflowError` in
`art::gc::Heap::CheckPreconditionsForAllocObject`. That proved the normal
8192-byte recovery reserve was consumed by Clang-O0 Microsoft-ABI frames, not
that the generated explicit check was wrong. A controlled 20,480-byte reserve
made switch pass but left nterp/JIT about 8 KiB short. The accepted fix uses
40 KiB only for non-`NDEBUG` Windows x86-64, leaves Release and non-Windows at
8192 bytes, and preserves more than 37 KiB on both Debug quick engines. Wine's
Debug runner used `-XX:ThreadSuspendTimeout=30000` only to isolate slow probe
recursion outside a safepoint; this is not a product runtime change.

The duplicate aggregate, host-info, dump-scan, and checksum files were removed
after their exact margins, `NO_DMP_FILES` outcome, host identity, and immutable
package identity were consolidated here. The ZIP remains outside VCS.
