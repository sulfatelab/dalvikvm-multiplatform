# LLP64 pointer and `jlong` audit

This maintained source and compile-graph audit protects Windows targets where
`long` is 32 bits but pointers and `jlong` are 64 bits. Passing an address
through `long` or `unsigned long` truncates its high half. The audit started
with W-020 on Windows x86-64 and applies equally to future Windows AArch64 and
ARM64EC profiles.

Preferred conversions are `ptr_to_jlong`, `jlong_to_ptr`, `uintptr_t`,
`intptr_t`, `LONG_PTR`, and `UINT_PTR`. A plain `long` is valid for an integer
value only when no pointer bits pass through it.

## Fast source audit

From the repository root:

```text
python3 tools/llp64_audit/scan_text.py
```

The command scans maintained Windows product source and fails if a high-risk
pointer/`jlong` conversion remains. Medium-confidence findings are printed for
review but do not fail the command.

## Full compile-graph audit

The unified frontend always configures CMake with
`CMAKE_EXPORT_COMPILE_COMMANDS=ON`, so the same target graph used for the
product supplies the audit database:

```text
python3 tools/build_art.py configure --target-id windows-x86_64-msvc
python3 -u tools/llp64_audit/scan_compile_db_warnings.py \
  out/windows-x86_64-msvc/RelWithDebInfo --jobs 16
```

The scanner replays each C/C++ translation unit with the plain Clang driver,
`-fsyntax-only`, `-Wvoid-pointer-to-int-cast`, and
`-Wint-to-void-pointer-cast`. It fails closed on any matching product-source
warning or any worker failure. Generated Markdown and JSON results stay under
`out/windows-x86_64-msvc/RelWithDebInfo/results/llp64-audit/`.

Parallelism 16 is deliberate for this frontend replay: an earlier 32-worker
run exhausted memory even though ordinary Ninja product builds use
`--parallel 32` safely.

The accepted 2026-07-17 Windows x86-64 baseline is summarized in `RESULT.md`.
Do not commit regenerated reports or compile databases.
