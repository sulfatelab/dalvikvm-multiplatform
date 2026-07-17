# Full Windows AST LLP64 cast audit (compile_commands + clang frontend)

- Method: **LibTooling-class** re-run of each Win64 `compile_commands` TU with
  `-fsyntax-only -Wvoid-pointer-to-int-cast -Wint-to-void-pointer-cast`
  (Clang only warns when integer is smaller than pointer — LLP64 `long` trap).
- TUs: **1426**
- Elapsed: 560.8s
- Hits (repo vendor/tools/compat/native only): **0**
- Worker failures: 0
- DBs: build/win64_phase1, build/win64_libcore_icu

## Findings

_None. No void*/smaller-integer casts in product repo paths._


## Notes

- This is stronger than regex: uses Clang's type size model on the real Win triple.
- System SDK hits (basetsd HandleToLong) are filtered by path.
- Pair with `scan_text.py` for `(jlong)(unsigned long)` spelling patterns.
- Optional custom LibTooling binary: see `llp64_cast_tool/` if libclang-*-dev is installed.

