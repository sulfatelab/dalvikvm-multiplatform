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
without defining `ART_WIN32_STACK_HIGH_WATER`. Other target architectures
remain non-applicable.

The authoritative Windows Server 2025 source projection and both variant
output trees contained zero reparse points. Aggregate JSON stores target IDs,
artifact names and hashes, exits, marker outcomes, mode counts, and validator
identity without absolute host paths.
