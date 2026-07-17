# Win64 JNI stubs (legacy / hybrid source pool)

## Product PE (required)

Do **not** ship `libcombined.dll` as `libicu_jni` / `libjavacore` / `libopenjdk`.

Use:

```bash
tools/win64/stage_native_modules.sh <dest>
tools/win64/stage_run_assets.sh <dest>
```

| Product module | Role |
|----------------|------|
| `icuuc.dll` / `icui18n.dll` / `icu_jni.dll` | Real AOSP ICU4C + android_icu4j natives (`NativeConverter`, metadata, …) |
| `javacore.dll` | Hybrid AOSP + Win bridges (may still link `win_fs`/`win_net` from this folder) |
| `openjdk.dll` / `openjdkjvm.dll` | Hybrid openjdk NIO + JVM_* helpers |

## Legacy

| File | Status |
|------|--------|
| `build_combined.sh` / `libcombined.dll` | **Non-product** (W-005 closed) |
| `native_converter.c` | **Obsolete** (W-006 closed); real converter in `icu_jni` |
| `win_fs_natives.c` / `win_net_natives.c` / `win_path.c` / `win_runtime_natives.c` | Still used as **source** linked into hybrid javacore/openjdk PE |
| `libcore_hello3.c` | Partial PE stubs for System/Runtime/math bits still linked into hybrids |

## Trackers

- W-005 closed — no multi-name libcombined product aliases
- W-006 closed — no product NativeConverter/ICU charset stubs
- W-016 closed — ship `run/icu/icudt72l.dat`
