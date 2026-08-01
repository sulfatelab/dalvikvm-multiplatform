# JIT unwind-lifecycle result

The JNI DSO observes compiled-method unwind lifecycle through ART. Its current
selector is exact `windows-x86_64-msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified | 2026-08-01 |

The canonical source passed the unified Windows cross catalog build. The
shell-free managed runner passed twice on Windows Server 2025, proving
invalidation, collection, exact-address reuse, recompilation, J-2 unwind-table
lifecycle, at least one collection, and no dump or temporary JIT file. Windows
AArch64 and ARM64EC are not implied.
