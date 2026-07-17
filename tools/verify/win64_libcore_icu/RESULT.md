# Win64 real ICU PE — RESULT

**Date:** 2026-07-17  
**Status:** **Phase A–B2 SUCCESS for product PE** — real ICU + hybrid javacore + AOSP openjdk NIO; **W-005 CLOSED** (no libcombined product aliases)

## What built

| DLL | Approx size | Notes |
|-----|-------------|--------|
| `icuuc.dll` | ~2.0M | ICU4C common; stubdata object linked into DLL; no `libandroidicuinit` |
| `icui18n.dll` | ~3.4M | ICU4C i18n |
| `icu_jni.dll` | (built) | Real `android_icu4j` libcore_bridge natives (NativeConverter, ICU4CMetadata, …) |

Harness: `tools/verify/win64_libcore_icu/`  
Configure/build:

```bash
source $WIN64_DEV_ENV/env.sh
cmake -S tools/verify/win64_libcore_icu -B build/win64_libcore_icu -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=$WIN64_CMAKE_TOOLCHAIN -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build/win64_libcore_icu -j$(nproc)
```

## Staging into ART package

```bash
cp build/win64_libcore_icu/{icuuc,icui18n,icu_jni}.dll build/win64_phase1/
cp build/win64_libcore_icu/icu_jni.dll build/win64_phase1/libicu_jni.dll
# javacore/openjdk still from jni_stubs/libcombined until Phase B
```

## Not done (Phase B+)

- ~~Real `libjavacore.dll` / `libopenjdk.dll`~~ **product PE** (W-005/L-001 closed)
- Full ICU data load path vs stubdata (file `ICU_DATA` / `icudt*.dat` packaging verification)
- Drop dual-name staging once ART load names settle
- Wire install into `package_win64_phase3.sh`

## Compat fixes landed for this work

- `compat/include/unistd.h` — `typedef int pid_t` on Win32
- `compat/include/byteswap.h` — new shim for ICU bridge sources

## Phase B0 — hybrid `javacore.dll` (2026-07-17)

**Status:** **BUILT + wine smoke OK** (CoreProbe, IoProbe)

| Piece | Approach |
|-------|----------|
| AOSP `Register.cpp`, ICU helpers, MethodHandle/VarHandle, NativeAllocationRegistry | Real sources |
| `libcore.io.Linux` | **Excluded** AOSP `libcore_io_Linux.cpp`; Win bridge registers ~50 methods from `win_fs`/`win_net` stubs |
| WinNT FS / sockets / OsConstants init | Same PE stub C sources linked into `javacore.dll` |
| Memory, NetworkUtilities, NativeBN, ExpatParser | **In PE** (L-001 2026-07-17) |
| AsynchronousCloseMonitor | **In PE** (Win monitor + JNI register; wine AsyncCloseProbe PASS) |
| OsConstantsHolder | **In PE** (Win multipath initConstants; wine OsConstantsProbe PASS) |
| full `libcore_io_Linux` | **Not yet** (Win bridge remains) |
| `libopenjdk.dll` | Still pure `libcombined` alias |

Artifact: `build/win64_libcore_icu/javacore.dll` (~92K)

### Smoke

```
showversion → ART version 2.1.0 x86_64
CoreProbe.done=ok
IoProbe.done=ok
```

## Phase B1 — hybrid `openjdk.dll` (2026-07-17)

**Status:** **BUILT + wine smoke OK** (CoreProbe, IoProbe)

| Piece | Approach |
|-------|----------|
| Zip Inflater/Deflater/CRC/Adler | Real AOSP ojluni |
| Float/Double, Object streams, Character, jdk.internal.misc.VM | Real AOSP |
| System/Runtime/math/time | PE stubs (`libcore_hello3` + `win_runtime_natives`) |
| `JVM_*` memory helpers | Standalone `openjdkjvm.dll` (process memory heuristics; not full ART heap yet) |
| NIO/EPoll/Unix FS/process | **Not included** (classic Socket via javacore Win bridge) |

Artifact: `build/win64_libcore_icu/openjdk.dll` (~113K), `openjdkjvm.dll` (~13K)

### Smoke (with real ICU + hybrid javacore + hybrid openjdk)

```
showversion OK
CoreProbe.done=ok
IoProbe.done=ok
```


## Phase B2 — AOSP openjdk Unix/NIO surface (2026-07-17)

**Status:** **BUILT + wine smoke OK** (CoreProbe, IoProbe with `ICU_DATA=run/icu`)

| Piece | Approach |
|-------|----------|
| NIO channels (`Net`, `SocketChannel`, `ServerSocketChannel`, `Datagram*`, `FileChannel`/`FileDispatcher`, `IOUtil`, `EPoll`, `PollArrayWrapper`, streams) | Real AOSP ojluni sources |
| CRT fd ↔ Winsock + select-based epoll | `compat/src/win64_socket_posix.c` + improved `poll`/`ioctl`/`fcntl` |
| `linux_close` / async-close / NativeThread | Win bridges under `vendor/libcore/multiplatform/windows/native/` |
| `JVM_*` I/O + socket helpers | Expanded `openjdkjvm_memory_standalone.c` |
| NIO.2 `sun.nio.fs` / async ports / UNIXProcess / UnixFileSystem_md | **Excluded** (non-goal / WinNT FS via javacore) |
| System/Runtime | Still PE stubs (`hello3` / `win_runtime`) |

Artifacts: `openjdk.dll` (~208K), `openjdkjvm.dll` (~38K)

### Smoke

```
ICU_DATA=run/icu  # required: full icudt72l.dat under run/icu (stubdata alone → U_FILE_ACCESS_ERROR)
showversion OK
CoreProbe.done=ok
IoProbe.done=ok
NetProbe.done=ok (after W-018 linger get/set in win_net_natives)
```

### ICU note

`icu_jni` `Register.cpp` now calls `udata_setCommonData(&U_ICUDATA_ENTRY_POINT)` on Windows; product smoke still needs **`ICU_DATA=run/icu`** with real `icudt72l.dat` until full data is embedded or path is hard-wired.


## Linger + ICU_DATA follow-up (2026-07-17)

- **W-018 CLOSED:** `getsockoptLinger` / `setsockoptLinger` in `tools/win64/jni_stubs/win_net_natives.c` + register table; wine NetProbe PASS.
- **ICU_DATA defaults:** phase3/phase4 runners already export `ICU_DATA=run/icu`; `package_win64_phase3.sh` now **requires** `run/icu/icudt72l.dat` (copies from build or vendor stubdata path fallback) and stages `icuuc`/`icui18n`/`openjdkjvm` when present.


## Product ICU data shipping (2026-07-17, W-016 CLOSED)

`icudt72l.dat` is a **required product asset** staged like `boot.jar`:

```bash
tools/win64/stage_run_assets.sh <dest_root> [build_dir]
# -> <dest>/run/boot.jar
# -> <dest>/run/icu/icudt72l.dat
```

Used by `package_win64_phase3.sh` and `install_into_phase1.sh`.  
`libicu_jni` `Register.cpp` defaults `ICU_DATA` to `<cwd>/run/icu` when unset if `icudt72l.dat` is present.


## Packaging (W-005 CLOSED)

Product trees use:

```bash
tools/win64/stage_native_modules.sh <dest> [build/win64_libcore_icu] [build/win64_phase1]
```

Stages real `icuuc`/`icui18n`/`openjdkjvm` + `icu_jni`/`javacore`/`openjdk`, then ART sonames `libicu_jni`/`libjavacore`/`libopenjdk` as copies of those real modules.  
`tools/win64/jni_stubs/libcombined.dll` is **legacy / non-product**.


## ICU charset path (W-006 CLOSED)

Product charset natives come from real AOSP bridge:

- `com_android_icu_charset_NativeConverter.cpp` in `icu_jni.dll`
- ICU4C in `icuuc.dll` / `icui18n.dll`
- Data: `run/icu/icudt72l.dat` (W-016)

`tools/win64/jni_stubs/native_converter.c` is obsolete and is **not** linked into product PE or the legacy combined stub build.


## Phase C0 — boringssl `crypto.dll` PE (L-002 partial, 2026-07-17)

**Status:** **BUILT + wine smoke OK**

| Artifact | Size | Notes |
|----------|------|--------|
| `crypto.dll` / `libcrypto.dll` | ~1.2M | AOSP boringssl `crypto_sources`, **OPENSSL_NO_ASM** (pure C) for reliable clang PE |
| `crypto_sha_smoke.exe` | ~14K | SHA-256 of fixed string |

```
crypto.ok=true
OPENSSL_VERSION=BoringSSL
sha256=ade21f7edb252b8418547a54bde2c3f3c56242f3f0ecd4ebbf917c5096d2bcce
CryptoSmoke.done=ok
```

Configure flag: `-DMDVM_WIN64_BUILD_CRYPTO=ON` (default ON in harness).

### Not done (remaining L-002)
- `win-x86_64` perlasm (llvm-ml) instead of OPENSSL_NO_ASM
- ~~`ssl.dll` / full TLS stack~~ **C1 PE done** (see below)
- ~~conscrypt `libjavacrypto` PE~~ **C1 PE done**; Java provider still missing from boot.jar
- HTTPS golden app (needs conscrypt Java + provider init)

## Phase C1 — `libssl` + conscrypt `libjavacrypto` PE (L-002 partial, 2026-07-17)

**Status:** **BUILT + wine LoadLibrary smoke OK** (native PE only; not full HTTPS)

| Artifact | Size | Notes |
|----------|------|--------|
| `libssl.dll` | ~475K | AOSP boringssl `ssl_sources`, OPENSSL_NO_ASM, links `libcrypto` |
| `libjavacrypto.dll` | ~257K | conscrypt JNI (`native_crypto.cc` + jniutil/jniload/netutil/close_monitor) |
| Export | — | `JNI_OnLoad` present on `libjavacrypto.dll` |

Configure: `-DMDVM_WIN64_BUILD_CRYPTO=ON` + `-DMDVM_WIN64_BUILD_SSL=ON` (defaults ON).

Win64 conscrypt header fixes (vendor nested):
- `compat.h`: do not redefine `ssize_t` when project compat already defines it
- `jniutil.h`: use ART `AttachCurrentThread(JNIEnv**, …)` form on `_WIN32`

Product staging (`stage_native_modules.sh`): optional single names  
`libcrypto.dll` / `libssl.dll` / `libjavacrypto.dll` (no short twins).

Wine smoke (cwd `build/win64_phase1`):

```
OK libcrypto.dll ... JNI_OnLoad=null
OK libssl.dll ... JNI_OnLoad=null
OK libjavacrypto.dll ... JNI_OnLoad=<non-null>
```

### C2/C3 blockers (honest)
- Current `run/boot.jar` has `javax/net/ssl/*` API types and **string** references to
  `com.android.org.conscrypt.OpenSSLProvider` / `JSSEProvider` (security provider list),
  but **no** `Lcom/android/org/conscrypt/` or `NativeCrypto` class bodies.
- ART does not preload `libjavacrypto`; platform path is `System.loadLibrary("javacrypto")`
  from conscrypt `NativeCryptoJni` when the Java provider initializes.
- Full HTTPS golden requires packaging conscrypt Java (jarjar `com.android.org.conscrypt`)
  onto bootclasspath (or extension jar) then a TLS golden (loopback or external).

## Phase C2 — conscrypt Java on bootclasspath (L-002 partial, 2026-07-17)

**Update:** With W-019 Math fix + Runtime.nativeLoad + jarjar prefix + JNI_OnLoad fixes,
wine `LoadCryptoProbe` constructs `OpenSSLProvider` successfully:
```
map=libjavacrypto.dll
System.load=ok
System.loadLibrary=ok
OpenSSLProvider.instance=AndroidOpenSSL version 1.0
LoadCryptoProbe.done=ok
```
`SslProviderProbe` still crashes on `Security.getProviders()` (default provider list path) — C2+ residual.


**Status:** **PACKAGED + partial runtime** (provider construction blocked by Math CriticalNative ABI)

### Packaging
- Script: `tools/bootjar/build_conscrypt_win64.sh`
  - Generates `NativeConstants.java` (host g++ + boringssl headers)
  - Compiles repackaged `com.android.org.conscrypt` + publicapi against boot classes
  - Merges into `/tmp/bootbuild/classes`, re-dexes, embeds `java/security/security.properties`
- Staged `run/boot.jar` contains:
  - `Lcom/android/org/conscrypt/` + `NativeCrypto` + `OpenSSLProvider`
  - resource `java/security/security.properties` (C2 provider list without BC)

### Runtime PE support
- `System.mapLibraryName("javacrypto")` → `libjavacrypto.dll` via `tools/win64/jni_stubs/libcore_hello3.c`
- Wine `System.load` / `System.loadLibrary("javacrypto")` **OK** (LoadCryptoProbe)
- `Class.forName(OpenSSLProvider)` **OK**

### Blockers remaining (not C2 packaging)
- **W-019:** `java.lang.Math` `@CriticalNative` (and FastNative double ABI) crashes on Win64 PE
  (`Math.ceil` aborts; HashMap/`OpenSSLProvider.<init>`/`NativeCrypto.<clinit>` trip on it)
- BootClassLoader resource `getResourceAsStream` still hits incomplete NIO.2 ZipFile path;
  Windows `Security` clinit **skips** resource load and uses `initializeStatic()`
- BC provider deferred (not on bootclasspath)
- Full HTTPS golden (C3) still open

### Wine evidence (LoadCryptoProbe)
```
map=libjavacrypto.dll
System.load=ok
System.loadLibrary=ok
OpenSSLProvider.class=com.android.org.conscrypt.OpenSSLProvider
# then abort in Math.ceil during OpenSSLProvider construction
```

## Single product DLL names (L-004 CLOSED)

Hybrid targets emit ART/product sonames directly:

| Target | OUTPUT_NAME |
|--------|-------------|
| `icu_jni` | `libicu_jni` |
| `javacore` | `libjavacore` |
| `openjdk` | `libopenjdk` |
| `openjdkjvm` | `libopenjdkjvm` |
| `crypto` | `libcrypto` |
| `ssl` | `libssl` |
| `javacrypto` | `libjavacrypto` |

`stage_native_modules.sh` stages only these (plus `icuuc`/`icui18n`) and removes short-name twins (`icu_jni.dll`, `javacore.dll`, …).


## Phase B3 — `libcore.io.Memory` + Linux Os expansion (2026-07-17)

**Status:** **BUILT + wine smoke OK** (CoreProbe / IoProbe / NetProbe)

| Piece | Change |
|-------|--------|
| AOSP `libcore_io_Memory.cpp` | Enabled in hybrid `libjavacore` (no longer empty register) |
| Linux Os bridge | Added mmap/munmap/msync/madvise/mincore/mlock/munlock, ftruncate, isatty, strerror, gai_strerror, environ, readlink, posix_fallocate |
| Link | `libjavacore` links `win64_socket_posix` (posix stubs: mmap family) |
| Design map | [win32_libcore_os_natives.md](../../../win32_libcore_os_natives.md) — Needed vs ENOSYS inventory |

Full AOSP `libcore_io_Linux.cpp` still **excluded** (Bionic header surface). Grow Win bridges per the map.


## Phase B4 — L-001 deepen Os Needed set (2026-07-17)

**Status:** **BUILT + wine smoke OK** (CoreProbe / IoProbe / NetProbe / GoldenApp)

Added Win hybrid implementations + RegisterNatives for:

- `chmod` / `fchmod`, `pipe2`, `preadBytes` / `pwriteBytes`, `readv` / `writev`, `sendfile`, `umaskImpl`
- `getsockoptTimeval` / `setsockoptTimeval`, `getsockoptByte` / `setsockoptByte`
- `inet_pton`, `if_nametoindex` / `if_indextoname`, `getnameinfo`
- `sendtoBytes` / `recvfromBytes`, simplified `sendmsg` / `recvmsg`

Inventory: [win32_libcore_os_natives.md](../../../win32_libcore_os_natives.md).

## L-002 Security.getProviders (2026-07-17 late)

Wine PASS:
- `SecStep17` BootClassLoader.loadClass(OpenSSLProvider)
- `SecStep3` Security.getProviders → AndroidOpenSSL / CertPathProvider / HarmonyJSSE
- digests/SecureRandom/AES-GCM/SSLContext.getInstance on AndroidOpenSSL

Root causes closed:
1. Win64 -Xint FastNative/native bridge routing (interpreter)
2. `FileChannelImpl.map0` Win64 LLP64 pointer truncation (`unsigned long` cast)

Residual: `SSLContext.init` needs `jks` KeyStore (SslProviderProbe exit 1).

## L-002 AndroidCAStore default KeyStore (2026-07-17)

Wine PASS:
- KeyStore.getDefaultType()=AndroidCAStore
- KeyManagerFactory/TrustManagerFactory init(null)
- SSLContext.init(null,null,null) → SslProviderProbe.done=ok

Note: empty system/user cacerts dirs until product ships roots; verify-path still needs CA population for real HTTPS.

## Product default CA bundle (2026-07-17)

Staged like ICU data:
- generator: `tools/win64/generate_cacerts.sh`
- hermetic assets: `tools/win64/assets/cacerts` (121 roots, subject_hash_old)
- stage: `tools/win64/stage_run_assets.sh` → `run/etc/security/cacerts`
- wine: TrustStoreProbe AndroidCAStore.size=121, acceptedIssuers=121, SSLContext.init ok

Residual HTTPS: `HttpsURLConnection` needs `com.android.okhttp.HttpsHandler` (not packaged yet).

## OkHttp handlers + HTTPS smoke (2026-07-17)

- Build: `tools/bootjar/build_okhttp_win64.sh` → boot.jar includes `com.android.okhttp.*` + okio (241 classes; multi-dex)
- Wine HttpsProbe:
  - handler.http=`HttpURLConnectionImpl`
  - handler.https=`HttpsURLConnectionImpl`
  - `https://example.com/` → status 200
- Multipath ASCII fallbacks: `java.net.IDN`, `java.text.Normalizer` (ICU4J tables still deferred)

## L-001 Expat / NativeBN / NetworkUtilities (2026-07-17)

**Status:** **BUILT into product `libjavacore.dll` + wine smoke OK**

| Module | Approach |
|--------|----------|
| `libcore.math.NativeBN` | Real AOSP `libcore_math_NativeBN.cpp` linked against product `libcrypto` (boringssl) |
| `org.apache.harmony.xml.ExpatParser` | Real AOSP ExpatParser + static vendored **libexpat 2.6.4** (`vendor/external/expat`) |
| `NetworkUtilities` | Real AOSP helpers (sockaddr ↔ InetAddress, msghdr conversion); Winsock/msghdr CMSG macros fixed in `compat/include/sys/socket.h` |
| Still empty registers | *(none for L-001 core modules)* |
| Still excluded | Full AOSP `libcore_io_Linux.cpp` (Win bridge remains), `cbigint` |

### Smoke (wine64, imageless `-Xint`)

```
BnProbe.done=ok
XmlProbe.done=ok elems=3 text=helloworld
CoreProbe.done=ok
NetProbe.done=ok
```

Probes: `tools/verify/win64_phase3/src/{Bn,Xml}Probe.java` via `build_one.sh` / `run_one.sh`.
`libjavacore.dll` ~335K after L-001 (was ~92K at B0).

## L-001 AsynchronousCloseMonitor (2026-07-17)

**Status:** **BUILT into product `libjavacore` + `libopenjdk` + wine smoke OK**

| Piece | Approach |
|-------|----------|
| JNI `libcore.io.AsynchronousCloseMonitor.signalBlockedThreads` | Real AOSP `libcore_io_AsynchronousCloseMonitor.cpp` (no longer empty register) |
| Monitor implementation | `multiplatform/windows/native/AsynchronousCloseMonitor_win.cpp` — thread list + `shutdown(SD_BOTH)` + best-effort `CancelSynchronousIo` |
| openjdk `NET_*` | `win_close.cpp` wraps blocking I/O with `AsynchronousCloseMonitor` (linux_close parity); `NET_SocketClose` signals then closes |
| Wake semantics | No POSIX signals; socket shutdown is the primary unblock path on Winsock |

### Smoke

```
AsyncCloseProbe.done=ok   # accept unblocked with SocketException; read EOF after peer close
NetProbe.done=ok
CoreProbe.done=ok
```

## L-001 OsConstantsHolder (2026-07-17)

**Status:** **BUILT into product `libjavacore` + wine smoke OK**

| Piece | Approach |
|-------|----------|
| JNI `android.system.OsConstantsHolder.initConstants` | Multipath `android_system_OsConstantsHolder_win.cpp` (all 121 holder fields) |
| Value ABI | **Android/bionic** numbers (not raw Winsock `AI_*`/`EAI_*`) so `win_net` getaddrinfo flag mapping stays consistent |
| Empty AOSP TU | Linux `android_system_OsConstantsHolder.cpp` still excluded (heavy Linux headers) |
| hello3 | Removed empty `Java_android_system_OsConstantsHolder_initConstants` exports |

### Smoke

```
OsConstantsProbe.done=ok  # AI_PASSIVE=1, AI_ADDRCONFIG=32, EAI_*, _SC_NPROCESSORS_*, …
DnsProbe.done=ok
NetProbe.done=ok
CoreProbe.done=ok
```

## L-001 CLOSED (2026-07-17)

**Exit criteria met:** product PE without `libcombined`; GoldenApp + charset (`CoreProbe`) + `LocaleProbe` PASS under wine.

| Product DLL | Role |
|-------------|------|
| `libjavacore.dll` | Hybrid AOSP + Win Os bridge + Expat/NativeBN/NetworkUtilities/AsyncClose/OsConstantsHolder |
| `libopenjdk.dll` | Hybrid AOSP NIO/zip + win_close AsyncClose |
| `libicu_jni.dll` / `icuuc` / `icui18n` | Real ICU PE |
| `libopenjdkjvm.dll` | JVM_* helpers |

**Intentional residual:** AOSP `libcore_io_Linux.cpp` not compiled on Win64; Os map uses Win bridges (needed=0). Crypto under L-002.
