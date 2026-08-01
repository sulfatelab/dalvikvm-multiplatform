# JIT lifecycle stress result

The JNI DSO stresses Windows x86-64 compilation, invalidation, collection,
reuse, lookup, and virtual unwind. Its selector is exact
`windows-x86_64-msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified | 2026-08-01 |

The canonical native source passed the unified cross catalog build and the
combined source/PE reviewer. The shell-free managed runner passed twice on
Windows Server 2025: eight cycles, eight collections, 216 compilations, 192
exact reuses, zero missing-live/stale-dead/unwind failures, no callback tables,
and passing JNI values. The work tree contained no dump or temporary JIT file.
