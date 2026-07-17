# bp2cmake

Converts AOSP `Android.bp` (Soong/Blueprint) modules into `CMakeLists.txt` for a
GNU/Linux (glibc) host build of a minimal ART runtime.

See `../../bp2cmake_linux_scope.md` for the full rationale. The short version: the
`.bp` files describe an Android/bionic build, and they are not the whole truth
(ART injects flags from Go). A faithful translation would be *wrong* for Linux.
So the converter is three layers:

| Layer | What | Where |
|-------|------|-------|
| 1 | Parse `.bp` + evaluate (`defaults`, vars, `arch`/`target` selects) against a fixed Linux config → normalized module graph | `bp2cmake/{lexer,parser,ast,evaluator}.py` |
| 2 | **Port-policy overlay** — the deliberate Android→Linux decisions (force SHARED, source swaps, dep rewrites, define overrides). Human-owned. | `//overlay` |
| 3 | Emit CMake from graph + overlay | `bp2cmake/emitter.py` |

Layer 2 is the durable, valuable asset: a submodule bump re-runs Layer 1 (the
drift-prone source lists), while Layer 2 (human judgment) rarely changes.

## Status

Prototype targeting `libbase` against the archive's 2023 submodule pins, so the
existing hand-written `native/cmake/libbase.cmake` serves as a validation
baseline (minus its known bugs — see the audit in `bp2cmake_linux_scope.md` §5.4).

## Layout

```
bp2cmake/
  lexer.py       tokenizer for the .bp grammar
  parser.py      recursive-descent parser -> AST
  ast.py         AST node types
  evaluator.py   Layer 1: resolve vars/defaults/selects -> module graph  (WIP)
  emitter.py     Layer 3: module graph + overlay -> CMake                (WIP)
tests/           pytest unit tests
```

## Running

```
python3 -m pytest tools/bp2cmake/tests -q
```
