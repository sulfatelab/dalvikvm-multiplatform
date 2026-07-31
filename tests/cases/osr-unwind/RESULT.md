# OSR unwind result

The `win32_osr_unwind_probe` validates emitted Windows x86-64 OSR and runtime
function records. Its handwritten ABI assumptions make it exact
`windows-x86_64-msvc`, not AArch64 or ARM64EC.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified | 2026-07-31 |

The source-path migration rebuilt the probe in the unified cross catalog. The
latest native Windows catalog acceptance remains the authoritative runtime run.
