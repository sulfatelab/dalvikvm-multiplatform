# OSR unwind result

The `win32_osr_unwind_probe` validates emitted Windows x86-64 OSR and runtime
function records. Its handwritten ABI assumptions make it exact
`windows-x86_64-msvc`, not AArch64 or ARM64EC.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified | 2026-08-01 |

The unified `stage:w002` gate passed natively on Windows Server 2025 x86-64.
The synthetic `RtlVirtualUnwind` probe resolves private transition-stub
addresses from the adjacent `art.pdb` through DbgHelp wide-character APIs; it
does not require those implementation symbols to become public `art.dll`
exports. The object/source reviewer also passed.

The managed OSR gate passed nterp and switch modes twice each. Every run
observed baseline and OSR compilation, the compiled-code jump, the exact
checksum, and the mode-specific completion path. The identical stage repeat
reported `ninja: no work to do` and passed all four W-002 CTest gates again.
Its aggregate JSON contains four successful records, stable input hashes, no
host absolute paths, and no dump files.
