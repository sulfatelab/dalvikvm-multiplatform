# Win64 Phase 2 (A3) — RESULT

**Status:** **PASSED** (wine64 gate, 2026-07-16)  
**Date:** 2026-07-16  
**Log:** `tools/verify/win64_phase1/hello_attempt54.log`

## Acceptance (A3)

```text
wine64 dalvikvm.exe … Hello
→ Hello from dalvikvm!
→ java.version=…
→ exit 0
```

**Met** under wine64 with imageless boot + interpreter (`-Xint`).

Observed:

```text
Hello from dalvikvm!
java.version=0
```

(`java.version=0` is an incomplete property table from PE libcore stubs; print path and Hello.main completed.)

## Command (canonical A3)

```bash
source /home/agent/Projects/win64-dev-env/env.sh
cd build/win64_phase1
# Stage PE JNI stubs (Phase-2 stand-in for libjavacore/libopenjdk/libicu_jni)
cp -f /tmp/win64_jni_stubs/libcombined.dll ./libjavacore.dll
for f in libopenjdk.dll libicu_jni.dll javacore.dll openjdk.dll icu_jni.dll; do
  cp -f ./libjavacore.dll "./$f"
done
cp -f "$WIN64_DEV_ENV/lib/libcxx/lib/c++.dll" .
export ANDROID_ROOT=run ANDROID_ART_ROOT=run ANDROID_I18N_ROOT=run
export ANDROID_DATA=run/data ICU_DATA=run/icu
WINEDEBUG=-all wine64 ./dalvikvm.exe \
  -Xbootclasspath:run/boot.jar -Xbootclasspath-locations:run/boot.jar \
  -Ximage:/nonexistent-no-boot-image -Xno-sig-chain -XjdwpProvider:none -Xint \
  -Xms64m -Xmx512m -cp run/hello.jar Hello
```

Rebuild PE stubs from repo sources:

```bash
bash tools/win64/jni_stubs/build_combined.sh
```

## What landed for A3

### Runtime / ABI
- dlmalloc WIN32 mmap override (MORECORE, low-4g non-moving)
- MemMap mprotect/msync/madvise Win64
- LinearAlloc / arenas low 4GB on Win64
- Win64 `ArtMethod::Invoke` → interpreter (no SysV quick stubs)
- `ExecuteSwitchImplAsm` SysV→MSVC bridge
- `ResolveJniEntryPoint` without `%gs` lookup stub
- Expanded `InterpreterJni` / `InterpreterJniGeneric` (incl. FJ/IJ/JL/LJ/VJ/VLJ/VJL/VJIIL/IJLILILZ)
- VEH + skip SignalCatcher; `-Xno-sig-chain` allowed on Windows
- `InitNativeMethods` loads PE `libicu_jni` / `libjavacore` / `libopenjdk`

### PE JNI stubs (Phase-2 only — not full libcore)
- Float/Double bit ops, System time/specialProperties, Linux passwd/uname/stat/getenv/sysconf/uid
- **NativeConverter** UTF-8/ISO-8859-1/US-ASCII/UTF-16 encode/decode + charsetForName
- `registerConverter` no-op with correct `(Object,long)` order
- `Linux.writeBytes` → `WriteFile` stdout/stderr
- `FileDescriptor.getAppend` / `isSocket`
- `UnixFileSystem.getBooleanAttributes0` / `checkAccess` / `canonicalize0` (PathClassLoader `-cp`)

## Limits / not Phase-2
- Real libcore PE (openjdk/icu natives) is **Phase 3**
- JIT / quick codegen Win64 ABI + GS TLS not required for A3
- Native Windows host run (not wine) still required for product acceptance beyond wine gate
- Many natives still missing; shorty fallback / stubs hide gaps deliberately for Hello

## Prior failures (historical)
- attempt47: charset ServiceLoader/ZipFile cycle (missing NativeConverter)
- attempt48: FATAL shorty `FJ` (getAveBytesPerChar)
- attempt49–50: hang / ClassNotFound without FS attribute natives
- attempt51: PASS with Hello on bootclasspath
- attempt53–54: PASS with `-cp run/hello.jar`

## Re-verification

Re-run on agent01 (2026-07-16, same command as above): **exit 0**, prints:

```text
Hello from dalvikvm!
java.version=0
```

## Durability

- PE stubs: `tools/win64/jni_stubs/` (+ `build_combined.sh`)
- Interpreter JNI helpers (vendor ignored tree): `archive-patches/win64_phase2_interpreter_jni.md`
- Port plan: `win64_art_port.md` rev19 Phase 2 DONE
