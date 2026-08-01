# Windows x64 libcore compatibility source pool

These regular source files are temporary inputs to the unified Windows product
graph. Build and stage them only through `tools/build_art.py`; this directory
does not own a compiler invocation, CMake graph, or package producer.

| Product module | Role |
|----------------|------|
| `icuuc.dll` / `icui18n.dll` / `icu_jni.dll` | Real AOSP ICU4C + android_icu4j natives (`NativeConverter`, metadata, …) |
| `javacore.dll` | Hybrid AOSP + Win bridges linking `win_fs`/`win_net` from this folder |
| `openjdk.dll` / `openjdkjvm.dll` | Hybrid openjdk NIO + JVM_* helpers |

## Retired alternatives

The one-DLL `libcombined` builder and the minimal `NativeConverter` stub were
removed after W-005/W-006 closed. The separate libcore/ICU CMake graph and
shell package/staging flow were removed after the unified graph built the full
DLL closure and the native W-004 gates passed.

The retained `win_fs_natives.c`, `win_net_natives.c`, `win_path.c`,
`win_runtime_natives.c`, `win_process_natives.c`, and `libcore_hello3.c` are
still compiled into the product. Their eventual relocation is source-layout
cleanup, not permission to recreate a target-specific build path.

## Trackers

- W-005 closed — no multi-name libcombined product aliases
- W-006 closed — no product NativeConverter/ICU charset stubs
- W-016 closed — stage `icudt72l.dat` through the unified runtime/test paths
