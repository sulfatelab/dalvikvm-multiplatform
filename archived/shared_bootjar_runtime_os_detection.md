# Shared boot.jar: Runtime OS detection for FileSystem selection

**Status:** **CLOSED** as D-001 — single shared boot.jar goal met (property inject + `VMRuntime.isWindowsOs` + dual FS + separators); name/values **LOCKED** (§11)  
**Date:** 2026-07-17  
**Decision context:** multipath will use **runtime selection** so Linux ART and Windows ART can share one `boot.jar` (instead of build-time WinNT overlay only).  
**Related:** L-005 (Linux Hello rejects WinNT boot), Option H WinNT FS, `../win32_filesystem.md`, `tools/bootjar/build_win64.sh`

---

## 1. Problem

Today product effectively has **two boots**:

| Artifact | `DefaultFileSystem` | Host that works |
|----------|---------------------|-----------------|
| Unix-style boot (e.g. `/tmp/vm/run/boot.jar`) | `UnixFileSystem` | Linux |
| Win product `run/boot.jar` | `WinNTFileSystem` (overlay) | Windows / wine |

A shared jar must contain **both** `UnixFileSystem` and `WinNTFileSystem` (and their natives on each host), and choose at runtime:

```text
DefaultFileSystem.getFileSystem()
  → Windows? WinNTFileSystem
  → else     UnixFileSystem
```

The non-trivial part is: **how does Java know the OS reliably, early enough, without depending on the wrong separators already being hardcoded?**

---

## 2. Timing constraints (must drive the design)

### 2.1 `File.fs` is extremely early

```java
// java.io.File
private static final FileSystem fs = DefaultFileSystem.getFileSystem();
```

`File` is touched during boot classpath / class loader bring-up. So:

- Selection runs during **class initialization**, not after app `main`.
- It must not require full `System` properties if those are not ready yet, **or** it must use a source that is ready independently of `File`.

### 2.2 `System` properties are multi-stage

In `System` unchangeable property construction (simplified order):

1. Native / runtime sources (`uname` → `os.name`, arch, …)
2. `specialProperties()` (native `user.dir`, library path, …)
3. ART `-D` / `Runtime` properties
4. **`AndroidHardcodedSystemProperties.STATIC_PROPERTIES` last**  
   Comment in tree: hardcoded values **must win** and cannot be overridden by `-D`.

Today multipath Windows hardcodes:

- `file.separator=\`
- `path.separator=;`
- `line.separator=\r\n`

That is incompatible with a shared jar unless those three stop being unconditional hardcodes.

### 2.3 Windows `os.name` is already available via uname path

Win product stub:

```c
// tools/win64/jni_stubs/libcore_hello3.c — makeUtsname
sysname = "Windows"
```

And `System` does:

```java
StructUtsname info = Libcore.os.uname();
p.put("os.name", info.sysname);  // "Windows" on Win multipath, "Linux" on Linux
```

So **`os.name` is a real multipath signal**, once `Libcore.os.uname` works.  
But see §2.1: `File` may initialize before this is a safe dependency if any circularity exists (`File` → FS → props → something that needs `File`).

**Design rule:** prefer an OS probe that does **not** go through `java.io.File` or classpath path parsing.

---

## 3. Detection approaches (multi-layer)

Use **layered signals**, ordered from strongest / earliest to weakest.  
Runtime selection should implement a small policy, not a single string compare buried in one place.

### Approach A — Compile-time / VM constants (strongest structural)

| Signal | Mechanism | When available | Notes |
|--------|-----------|----------------|-------|
| ART native build flag | `ART_TARGET_WINDOWS` / `_WIN32` in natives | always on that PE/ELF | Not visible to pure Java unless exported |
| Java build constant | `dalvik.system.VMRuntime` or libcore `OsConstants` / generated `Platform` class | class load | Can be baked per **native** lib, not per boot.jar |
| System property injected by ART | e.g. `dalvik.vm.multiplatform.internal.os=windows` from `dalvikvm`/`libart` multipath startup | Runtime properties vector | Keeps **one boot.jar**; PE differs |

**Recommendation:** export a **tiny pure-Java-readable fact** from the VM/native side:

- Preferred name: `dalvik.vm.multiplatform.internal.os` = `windows` | `unix` (see §11)
- Set only by native `dalvikvm` / `libart` / `libcore` init **before** Java `System` finishes hardcodes, **or** as a non-overridable special property.

This is the cleanest multipath answer: **same boot.jar bytes**, different native injectors.

### Approach B — `os.name` / `uname` (standard Java, already multipath)

| Host | Expected `os.name` |
|------|--------------------|
| Linux | `Linux` (real uname) |
| Windows multipath | `Windows` (current stub) |
| Fuchsia / others | real sysname |

Detection sketch:

```java
static boolean isWindowsOs() {
  String os = System.getProperty("os.name", "");
  // OpenJDK-compatible prefix check
  return os.regionMatches(true, 0, "Windows", 0, "Windows".length());
}
```

**Pros**

- Familiar to OpenJDK / app code
- Already wired through `Libcore.os.uname()`
- Works for tests that set `os.name` carefully (if hardcodes allow)

**Cons / hazards**

- Depends on `System` property init order
- If hardcoded separators remain Windows-only, Linux falsely configured even when `os.name=Linux` is correct
- Early `File` init may run before props exist → cannot call `System.getProperty` safely unless guarded

**Guard pattern if using properties:**

```java
// Only if System is initialized enough; else fall through to native probe
if (System.propsReadyEnough()) { ... }
```

(In practice, multipath should add an explicit early probe C/D rather than relying on partial `System`.)

### Approach C — Pure native JNI probe (best early, independent of props)

Add a **package-private** or `@hide` native used only by `DefaultFileSystem`:

```java
// java.io.DefaultFileSystem
private static native boolean isWindowsNative();
```

Implementations:

| Library | Behavior |
|---------|----------|
| Linux `libjavacore` / ojluni natives | return `false` (`#if !defined(_WIN32)`) |
| Windows PE natives | return `true` (`#if defined(_WIN32)`) |

Or use existing pattern without new method:

```c
#if defined(_WIN32)
  // Windows
#else
  // Linux
#endif
```

inside a single multipath native that both builds ship.

**Pros**

- Available at first `File` class init
- No dependency on `os.name` string quality
- Matches ART’s own `_WIN32` reality (same as PE vs ELF)

**Cons**

- Requires native registration in both OS product graphs
- Must not be spoofable by apps (keep package-private / non-public)

**Recommendation:** **C is the primary selector for `DefaultFileSystem`.**

### Approach D — Environment / filesystem heuristics (fallback only)

Useful as diagnostics or last resort, **not** primary:

| Heuristic | Windows-ish | Linux-ish | Spoof risk |
|-----------|-------------|-----------|------------|
| `System.getenv("OS")` | often `Windows_NT` | usually unset | medium |
| `System.getenv("SystemRoot")` / `WINDIR` | present | absent | medium |
| Existence of `C:\` vs `/proc` | weak on wine | weak in containers | high |
| Path of `java.home` / `ANDROID_ROOT` | `run\` vs `run/` | same product layout may be `/` on both under wine | high |

Wine note: many Windows env vars exist under wine while the process is still a Win PE. Heuristics that look at host Linux `/proc` from a Win PE are wrong.

**Do not** use host-fs heuristics for PE-on-wine vs real Win.

### Approach E — Security / crypto manager “platform” classes

Conscrypt `Platform` already has android vs openjdk splits. That is a **separate** compile-time product dimension (android jarjar vs openjdk), not Linux vs Windows.

Do **not** overload “android Platform” to mean “Windows OS”.

### Approach F — Class presence (anti-pattern for shared jar)

```java
Class.forName("java.io.WinNTFileSystem"); // always present in shared jar
```

Once both classes ship, presence means nothing. Reject this approach.

---

## 4. Recommended multi-approach policy

Implement selection as a **stable priority ladder**:

```text
1. Native isWindowsNative() / compile flag in JNI   (authoritative)
2. ART-injected property `dalvik.vm.multiplatform.internal.os` = `windows`|`unix` (authoritative if set)
3. os.name starts with "Windows"                     (consistency / tests)
4. Fail closed to UnixFileSystem                     (safer default for CI Linux)
```

### 4.1 Pseudocode for shared `DefaultFileSystem`

```java
class DefaultFileSystem {
  public static FileSystem getFileSystem() {
    if (OsDetection.isWindows()) {
      return new WinNTFileSystem();
    }
    return new UnixFileSystem();
  }
}
```

```java
final class OsDetection {
  private static final boolean IS_WINDOWS = detect();

  static boolean isWindows() { return IS_WINDOWS; }

  private static boolean detect() {
    // 1) Native PE/ELF truth (preferred)
    try {
      if (hasNativeProbe()) {
        return isWindowsNative();
      }
    } catch (Throwable ignored) { /* fall through */ }

    // 2) VM-injected explicit property (optional)
    String artOs = getArtTargetOsOrNull(); // not System.getProperty if unsafe;
                                            // or System after init
    if (artOs != null) {
      return artOs.equalsIgnoreCase("windows");
    }

    // 3) uname-backed os.name when available
    String os = safeOsName();
    if (os != null) {
      return os.regionMatches(true, 0, "Windows", 0, 7);
    }

    // 4) Default Unix (Linux host oracle / Android heritage)
    return false;
  }
}
```

Cache in a `static final boolean` so detection runs once.

### 4.2 Separators and properties (must move with FS selection)

Shared boot.jar **cannot** keep unconditional Windows hardcodes.

**Policy:**

| Property | Source after shared-boot work |
|----------|-------------------------------|
| `os.name` | `uname().sysname` (already) |
| `file.separator` | `\` if Windows else `/` — **not** static hardcode, or hardcode only non-OS keys |
| `path.separator` | `;` if Windows else `:` |
| `line.separator` | `\r\n` if Windows else `\n` |

Implementation options:

1. **Remove** the three keys from `AndroidHardcodedSystemProperties` and set them next to `os.name` in `System` property setup from the same `OsDetection` / native probe.  
2. Or keep hardcodes as **Unix defaults** (Android historical) and have Windows native `specialProperties()` / ART inject overrides **before** hardcodes — **but** current hardcodes intentionally beat `-D`. So Windows would need hardcodes to become conditional or to stop including separators.

**Preferred:** option 1 — separators derived from the same OS probe as `DefaultFileSystem`.

`WinNTFileSystem` already reads:

```java
slash = props.getProperty("file.separator", "\\").charAt(0);
semicolon = props.getProperty("path.separator", ";").charAt(0);
```

So correct properties + WinNT class selection must agree.

---

## 5. How ART / natives should expose the signal

### 5.1 Minimal multipath API (recommended)

Add one of:

**Variant M1 — JNI on `DefaultFileSystem` / `OsDetection`**

```c
// always linked into libjavacore product on both OSes
JNIEXPORT jboolean JNICALL
Java_java_io_OsDetection_isWindowsNative(JNIEnv*, jclass) {
#if defined(_WIN32)
  return JNI_TRUE;
#else
  return JNI_FALSE;
#endif
}
```

**Variant M2 — ART property at VM start**

In Windows `dalvikvm` PE only, push:

```text
dalvik.vm.multiplatform.internal.os=windows
```

into `Runtime` properties list (same channel as other `runtime.properties()`).  
Linux host builds omit it or set `linux`.

M1 is simpler for `File` static init.  
M2 is nicer for pure-Java tests and debugging (`System.getProperty` once props exist).

**Do both if cheap:** M1 for FS selection, M2 for observability.

### 5.2 Keep `uname` honest

| Build | `sysname` |
|-------|-----------|
| Linux | real `uname` (`Linux`) |
| Windows multipath | `"Windows"` (current) — **keep** |
| wine PE | still `"Windows"` (correct: guest OS is Windows ABI) |

Never set Win PE `sysname` to `Linux` just because the host kernel is Linux.

### 5.3 What not to use

- Host `/proc` from Win PE  
- `Class.forName("WinNTFileSystem")`  
- `file.separator` already set (circular: we need OS to set separator)  
- Conscrypt Platform android/openjdk flavor  

---

## 6. Interaction with wine

Wine runs **Windows PE** ART:

- Native `_WIN32` → true  
- `os.name` → `Windows`  
- separators → `;` `\` `\r\n`  
- FS → `WinNTFileSystem`  
- Host is Linux, but product ABI is Windows — **correct**

Shared boot.jar on wine should behave as Windows, not as Linux host oracle.

L-005 Linux gate uses **ELF** `build/native/dalvikvm` → Unix selection.

---

## 7. Testing matrix for detection

| Runtime | Expected `isWindows` | Expected FS | Expected `path.separator` |
|---------|----------------------|-------------|---------------------------|
| Linux ELF multipath | false | Unix | `:` |
| Win PE real host | true | WinNT | `;` |
| Win PE under wine | true | WinNT | `;` |
| Shared boot.jar hash | identical bytes on both | selection differs | props differ |

Gates:

1. **L-005** on Linux with **the same jar bytes** used for Win product  
2. Win wine Hello + `File.pathSeparator` / absolute `C:\` probes  
3. Unit-level `OsDetection` tests with native probe only (no prop spoofing)

---

## 8. Migration steps (implementation later)

1. Introduce `OsDetection` (Java) + `isWindowsNative` (JNI) in libcore multipath.  
2. Change `DefaultFileSystem.getFileSystem()` to runtime branch; ship **both** FS classes always.  
3. Stop overlay-only WinNT-as-Default in `build_win64.sh` (or make overlay a no-op).  
4. Move separators/line.separator out of unconditional hardcodes; set from `OsDetection`.  
5. Produce **one** `boot.jar`; point Linux gate + Win stage scripts at it.  
6. Close dual-boot special cases in packaging docs / L-005 comments.

Non-goals for first shared jar:

- NIO.2 `DefaultFileSystemProvider` Windows implementation (still Linux-hardwired; separate work)  
- Identical `boot.art` images  

---

## 9. Answer summary: “How can Java tell Linux vs Windows?”

**Best multipath answer (use together):**

1. **Primary:** native compile/ABI probe (`_WIN32` / JNI `isWindowsNative`) — truth for PE vs ELF.  
2. **Secondary:** ART-injected `dalvik.vm.multiplatform.internal.os` = `windows`|`unix` (authoritative multipath enum; §11 LOCKED).  
3. **Tertiary:** `os.name` / `uname().sysname` (`Windows` vs `Linux`) once `System` props exist — matches OpenJDK expectations.  
4. **Default:** Unix if all else fails (protect Linux CI).  

**Do not** rely on build-time jar overlays as the long-term OS switch.  
**Do not** let `AndroidHardcodedSystemProperties` force Windows separators in a shared jar.

That combination makes one `boot.jar` feasible without lying under wine and without breaking L-005.

---

## 10. Open questions (before coding)

1. ~~Canonical property name/values~~ — **RESOLVED §11:** `dalvik.vm.multiplatform.internal.os` = `windows`|`unix` (reject `mp`, `posix`, `linux` as product enum).  
2. Should separators be set in Java from `OsDetection`, or only from native `specialProperties()`?  
3. Is early JNI registration for `OsDetection` guaranteed before first `File` use on both PE and ELF product graphs?  
4. Should Arm64EC / future ABIs be a third value now (`windows-arm64ec`) or fold under `windows` until needed?

---

*Design only — no runtime code required by this document. Property contract is locked; FS selection code is not yet implemented.*

---

## 11. Preferred VM property: name and enum (**LOCKED**)

### 11.1 Decision (product-confirmed 2026-07-17)

Long + explicit wins over short. **`internal` is intentional** — this is a multipath VM
contract, not something third-party apps are expected to read or set.

```text
dalvik.vm.multiplatform.internal.os = "windows" | "unix"
```

Injected from `libart` / `dalvikvm` during startup into ART’s properties list
(the same channel as `-D…` / `Runtime::GetProperties()` → `System` unchangeable
props via `runtime.properties()`).

### 11.2 Naming review (resolved)

Product preference: **it does not hurt to be long**; short `mp` is ambiguous;
`internal` documents “not expected to be used by others.”

| Candidate | Pros | Cons |
|-----------|------|------|
| **`dalvik.vm.multiplatform.internal.os`** ★ **LOCKED** | Explicit multipath + internal; final segment is the enum | Longer key (acceptable by design) |
| `dalvik.vm.multiplatform.internal.osfamily` | Emphasizes family vs `os.name` | Slightly heavier; not chosen |
| `dalvik.vm.multiplatform.internal.ostype` | Same idea as above | `type` is redundant with enum values |
| `dalvik.vm.mp.os` | Short | **`mp` is ambiguous** (multiprocess, multipath, memory pool…) — **rejected** |
| `dalvik.vm.os` | Short | Collides conceptually with `os.name` |
| `android.art.os` | ART-centric | Less aligned with `dalvik.vm.*` knobs |

**Canonical key:**

```text
dalvik.vm.multiplatform.internal.os
```

Rationale:

1. Stays under **`dalvik.vm.*`** (ART/libcore house style for VM knobs).
2. **`multiplatform`** is fully spelled out — no `mp` ambiguity; length is intentional.
3. **`internal`** documents intent: set by ART/libart multipath startup; apps/framework must not treat it as a supported public switch (still readable as a system property, but not a stable app API / not expected for external use).
4. Final segment **`os`** (not `ostype`) — the value *is* the OS family enum.

Optional synonym only if debugging needs a human phrase in docs; do **not** ship two live keys.

### 11.3 Enum values

Use a **closed lowercase enum**:

| Value | Meaning | Selects |
|-------|---------|---------|
| **`windows`** | Win32/Win64 PE product (including wine guest) | `WinNTFileSystem`, `\`, `;`, `\r\n` |
| **`unix`** | ELF host / POSIX-like multipath (Linux CI, future *BSD if any) | `UnixFileSystem`, `/`, `:`, `\n` |

**Why `unix` not `linux`:**

- Matches `UnixFileSystem` class naming in libcore.
- Leaves room for non-Linux POSIX hosts without a third boot policy.
- Avoids implying `os.name` must equal `"Linux"` (Fuchsia multipath would still be `unix` FS if ever needed).

**Why not `Windows` / `Unix` capitals:** stable machine enum; compare with `equals`, not locale-sensitive case folding beyond an explicit `toLowerCase(Locale.ROOT)`.

**Forbidden / reserved for later (do not invent ad hoc):**

- `win`, `win32`, `win64` — fold into `windows`
- `linux`, `android` — not OS-family for FS selection
- empty / missing — treat as “unset”, fall through to native probe then default `unix`

### 11.4 Injection point (libart / dalvikvm)

```text
Windows PE build:
  properties_.push_back("dalvik.vm.multiplatform.internal.os=windows");

Linux ELF multipath build:
  properties_.push_back("dalvik.vm.multiplatform.internal.os=unix");
```

Rules:

1. Set **unconditionally** for multipath product builds (not only when debugging).
2. Set **before** Java `System` consumes `runtime.properties()` (normal ART startup order already does this).
3. Document that **command-line `-Ddalvik.vm.multiplatform.internal.os=…` must not override** product truth for FS selection — either:
   - ignore user `-D` for this key when native probe disagrees, or
   - put the key into a non-overridable channel (same spirit as hardcoded props).

### 11.5 How Java should read it

```java
// Conceptual — OsDetection
private static final String PROP = "dalvik.vm.multiplatform.internal.os";

static Boolean osFromVmProperty() {
  // Prefer a channel that works after System props exist:
  String v = System.getProperty(PROP);
  if (v == null || v.isEmpty()) return null;
  v = v.toLowerCase(Locale.ROOT);
  if (v.equals("windows")) return Boolean.TRUE;
  if (v.equals("unix")) return Boolean.FALSE;
  // Unknown value: log once, treat as unset
  return null;
}
```

**Still keep native `_WIN32` probe as primary** for the earliest `File` static init if property read is unsafe; once props exist, `dalvik.vm.multiplatform.internal.os` must **agree** with native probe (DCHECK / log error on mismatch).

### 11.6 Relationship to `os.name`

| Property | Role |
|----------|------|
| `os.name` | Kernel/guest marketing string from `uname` (`Linux`, `Windows`, …) — OpenJDK-compatible |
| **`dalvik.vm.multiplatform.internal.os`** | Closed multipath enum for boot policy (`windows` / `unix`) |

Never parse `os.name` as the only source for product FS selection if `dalvik.vm.multiplatform.internal.os` is present.

### 11.7 Final recommended contract

```text
Name:   dalvik.vm.multiplatform.internal.os
Type:   system property (ART Runtime properties / -D channel)
Values: "windows" | "unix"   (exact, lowercase)
Setter: libart / dalvikvm multipath startup (host build)
Getter: `VMRuntime.isWindowsOs` / DefaultFileSystem / System separator setup
Default if unset: native probe, else "unix"
Stability: internal multipath contract — not a public app API
```

Reject abbreviated `dalvik.vm.mp.os` (`mp` is ambiguous). Prefer `…os` over `…ostype`. Values stay `windows`|`unix` (not `posix`/`linux`).



---

## 12. Implementation status (Phase 1)

Landed 2026-07-17:

| Piece | Location |
|-------|----------|
| Property inject | `vendor/art/runtime/runtime.cc` — if unset, push `dalvik.vm.multiplatform.internal.os=windows` on PE / `unix` on ELF |
| OS helpers | `dalvik.system.VMRuntime` — `isWindowsOs()`, `multiplatformOs()`, `isWindowsOsFromProperties`, constants `MULTIPLATFORM_OS_PROP` / `OS_WINDOWS` / `OS_UNIX` (naked methods on VMRuntime; no `java.lang.OsDetection`) |
| Detection ladder | `VMRuntime.properties()` → System props / `os.name` → default `unix` |
| `DefaultFileSystem` | runtime branch via `VMRuntime.isWindowsOs()` |
| Separators | removed from hardcodes; set in `System.initUnchangeableSystemProperties` via `VMRuntime.isWindowsOsFromProperties` |
| Boot packaging | `tools/bootjar/build_win64.sh` no longer applies WinNT-only overlay; stages shared jar |
| L-005 | accepts shared jar (Unix + optional WinNT with multipath helpers) |

Still out of scope: NIO.2 `DefaultFileSystemProvider` Windows path.


---

## 13. Close notes (D-001)

**Closed 2026-07-17.** D-001’s success criterion is **one multipath boot.jar**, not a dual-host proof matrix of “WinNT on Windows and Unix on Unix.”

Met:

- One packaging path stages a jar containing both `UnixFileSystem` and `WinNTFileSystem`
- Runtime selection via `VMRuntime.isWindowsOs()` / `dalvik.vm.multiplatform.internal.os`
- Separators derived at `System` init (not unconditional hardcodes)
- Linux L-005 imageless Hello PASS on those shared multipath bytes

Out of scope for this close (ordinary product smoke later):

- Wine/host Hello asserting WinNT selection on PE
- Formal dual-host golden that both FS backends are exercised under product packaging
