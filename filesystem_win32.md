Product tree: **dalvikvm-multiplatform** (nested `vendor/libcore` on `artmp_*`).

# Feasibility: Win64 Path / Filesystem Model for ART + libcore

> **Scope:** Path semantics and file I/O for native Win64 ART (PE32+, no WSL).  
> **Related:** [win32_port.md](win32_port.md) §4.7.1 (product path mandate), Phase 3 libcore bring-up.  
> **Date:** 2026-07-16 (rev 4)  
> **Status:** **Decision locked — Option H (Hybrid).** Windows NIO.2 provider is a **non-goal for now**. Path/FS foundations + wine path gates landing (see `tools/verify/win64_phase3/RESULT.md`).

## 0. Why a separate document

Win64 path handling is **not** “one FileSystem class.” libcore and ART open paths through **three loosely coupled layers**. Choosing `UnixFileSystem` vs `WinNTFileSystem` only fixes layer A. Mixed paths (`C:\User\example/some/file`) are a **product mandate** (see win32_port §4.7.1) and force a clear design before Phase 3 coding.

This note answers:

1. How **libcore** and **libart** use path/filesystem APIs today.  
2. What OpenJDK/ojluni Windows code can be **reused**.  
3. Whether to keep `UnixFileSystem`, port `WinNTFileSystem`, or hybridize.  
4. A phased feasibility plan and acceptance cases.

---

## 1. Three layers (must not be conflated)

```text
  App / launcher / -cp / properties
           │
           ▼
 ┌─────────────────────────────────────┐
 │ A. java.io.File + FileSystem        │  path *syntax* (absolute, normalize,
 │    DefaultFileSystem → UnixFileSystem│  parent/name, separator, list attrs)
 │    (+ optional java.nio.file later) │
 └─────────────────┬───────────────────┘
                   │ f.getPath() strings
                   ▼
 ┌─────────────────────────────────────┐
 │ B. IoBridge / Libcore.os / Linux    │  open/read/write/close/stat/access…
 │    FileInputStream/OutputStream     │  ~ bulk of real I/O on Android libcore
 └─────────────────┬───────────────────┘
                   │ path C strings / fds
                   ▼
 ┌─────────────────────────────────────┐
 │ C. ART C++ OS::Open* / ZipArchive / │  boot.jar, dex, oat, vdex, images
 │    MemMap::MapFile / FdFile         │  (not java.io)
 └─────────────────────────────────────┘
```

| Layer | Owner | Path job | Byte I/O job |
|-------|--------|----------|--------------|
| **A** | `java.io.FileSystem` | Syntax, absolute, normalize, join, attributes façade | Some ops via JNI; many redirected to B on Android |
| **B** | `libcore.io` | Treats paths as opaque OS strings | Primary stream I/O |
| **C** | `libartbase` | OS pathname for jars/dex/maps | CRT/`open`/`CreateFile` style |

**Implication:** Porting only OpenJDK `WinNTFileSystem` does **not** make `System.out`, `FileInputStream`, or `DexPathList` work. Implementing only `Linux.open` does **not** make `new File("C:\\a\\b").isAbsolute()` true.

---

## 1.5 Canonical path policy (product decision)

### Inputs we must accept

| Kind | Examples | Notes |
|------|----------|--------|
| Relative, `/`-style (Android/Java common) | `file.txt`, `rel/path/to/classes.dex`, `../just/works.txt` | Primary for this repo’s run scripts and many Java libs |
| Relative, `\`-style | `rel\path\to\file.txt` | Native Windows code / users |
| Absolute Windows | `C:\User\somefile.exe` | Drive + backslash |
| **Mixed** absolute | `C:\User/somefile.exe`, `C:\User\admin/.ssh/known_hosts` | **Mandatory** — Win32 and Java often combine roots with `/` joins |
| UNC (later / as needed) | `\\server\share\a.jar`, `//server/share/a.jar` | Same normalize rules; v1 can be “best effort” after drive paths |

Zip **entry** names stay `/`-only (spec). That is not a filesystem path.

### Outputs for absolute / canonical resolution

When a program asks for an absolute or canonical form of a relative path (e.g. `new File("../file.txt").getAbsolutePath()` / `getCanonicalPath()`):

| Return | Verdict |
|--------|---------|
| `C:\path\to\file.txt` (or current drive + resolved dirs) | **Preferred product form** |
| `C:/path/to/file.txt` | Acceptable intermediate if FileSystem normalizes; prefer `\` as `file.separator` on Win64 product builds (WinNT-class) |
| `//?/C:/path/to/file.txt` or `\\?\C:\...` | **Do not return by default** — extended syntax is for kernel long-path edge cases, not app-facing Java paths |
| `/path/to/file.txt` (POSIX absolute) | **Wrong for Win64 product** — pretends we are still Unix |

**Rationale:** Win64 ART is a **Win32-platform-aware** runtime. Programs that call `getAbsolutePath()` on Windows generally expect a Windows path. They are **unlikely** to require POSIX absolutes. If ART or libcore mis-handles `C:\…` (e.g. string joins that assume `/`, dalvik-cache name mangling, naive `:` splits), **fix those call sites** — do not paper over them by forcing a Unix path façade forever.

### Normalization contract (all of layers A/B/C)

Shared rule before Win32 APIs and for Java path math:

1. Treat **`/` and `\` as the same separator** when parsing.
2. Preserve drive prefix (`X:`) and UNC prefix.
3. Collapse redundant separators; resolve `.` / `..` for **canonical** (and for absolute resolve against `user.dir`).
4. Emit **normal Win32 paths** for absolute results: `C:\a\b` style (no `\\?\` unless an explicit long-path API opt-in is added later).
5. `user.dir` / `java.home` on Win64 product: real Windows directories (`GetCurrentDirectoryW` / install dir), not fake `/` or Linux wine paths in the final product story (wine gates may still see `Z:\…` — that is test env, not the model).

### Properties (Win64 product)

| Property | Product value |
|----------|----------------|
| `file.separator` | `\` |
| `path.separator` | **`;`** (Windows / OpenJDK convention) |
| `user.dir` | Windows absolute cwd, e.g. `C:\work\app` |

`File.separatorChar` follows FileSystem → WinNT-class → `\`. Relative inputs written with `/` still parse (normalize accepts both).  
`File.pathSeparator` / `pathSeparatorChar` → **`;`**.

### Classpath / bootclasspath list separator — **`;` not `:`**

**Decision:** On Win64 product builds, multi-path lists use **`;`**, same as OpenJDK on Windows.

#### Why `:` is unsafe on WinNT

| Input | Split on `:` | Result |
|-------|----------------|--------|
| `C:\a.jar:C:\b.jar` | naive | `C`, `\a.jar`, `C`, `\b.jar` — **broken** |
| `C:/a.jar:C:/b.jar` | naive | same class of bug (`C` / `/a.jar` / …) |
| `C:\a.jar` alone | single element | OK, but multi-jar with drives is the common real case |
| Drive-aware splitter | possible | Fragile (edge cases: `C:`, relative `C:foo`, mixed quoting); easy to get wrong in **both** Java and ART C++ |

Using `:` as the list separator on a platform where **absolute paths contain `:`** is inherently risky. Fixing every splitter is worse than using the separator Windows Java already standardized.

#### Why `;` is the right default

- OpenJDK Windows: `path.separator=;` and `-cp a.jar;b.jar`.
- Does **not** appear in drive letters or normal Win32 path bodies.
- Works for relative and absolute:

  - `run\a.jar;run\b.jar`
  - `run/a.jar;run/b.jar`
  - `C:\libs\a.jar;C:\libs\b.jar`
  - `C:\User/admin/.ssh/../lib\x.jar;D:/other/y.jar`

#### What must change in this tree (today hardcodes `:`)

| Site | Today | Win64 product |
|------|--------|----------------|
| `parsed_options.cc` `-cp` help + storage | string as given | document `;`; store raw string |
| `ParseStringList<':'>` for `-Xbootclasspath`, locations, images | split `:` | **`ParseStringList<';'>`** (or platform constant) under `ART_TARGET_WINDOWS` |
| `Runtime` `Split(class_path_string_, ':')` | `:` | **`;`** on Windows |
| env `BOOTCLASSPATH` / similar | `ParseStringList<':'>` | `;` on Windows |
| `DexPathList` / `PathClassLoader` | `File.pathSeparator` | **automatic** once FileSystem returns `';` |
| `java.class.path` property | from runtime | join with `;` on Windows |
| Phase-2 / Linux scripts | `a.jar:b.jar` | Win64 scripts/docs use `a.jar;b.jar` |

Linux/Android port **keeps** `:`. This is an intentional **OS divergence**, not a unified ART ABI across OSes.

#### Dual-accept (`:` and `;`)?

**Not required for v1.** Optional migration sugar later (e.g. accept `:` only for lists with **no** `X:` drive patterns) is complexity with little benefit if we document `;` clearly. Prefer **strict `;`** on Win64.

#### Explicit non-goals

- Do not keep `path.separator=:` “for Android compatibility” on Win64 — it fights drive paths.
- Do not return `//?/` paths to dodge list-separator issues.

### Will apps be “unhappy” with `C:\…` absolutes?

**Unlikely for a Win32-targeted VM.** Typical unhappiness sources:

| Concern | Response |
|---------|----------|
| Android code assumes absolute ⟺ starts with `/` | Fix or gate such checks on Win64; File.isAbsolute() must use Win rules |
| `Character.isLetter` used for drive letters | **Broken without ICU** on imageless ART (`isLetter('C')==false`). Use ASCII `isDriveLetter` only |
| Regex / split on `/` only | Prefer `File` API; fix hot spots when found |
| ART inserts `/` into Windows abs paths | Fix `file_utils` / image path helpers under `kIsTargetWindows` |
| Wine shows `Z:\…` | Acceptable on agent01; product docs use real drive letters |

### Explicit non-policy

- Not a “Linux path ABI on Windows.”  
- Not “always return forward slashes for friendliness.”  
- Not extended-length `\\?\` as the default Java-visible form.

## 2. What this tree has today

### 2.1 Layer A — java.io

| Artifact | Location | Notes |
|----------|----------|--------|
| `FileSystem` abstract API | `vendor/libcore/ojluni/.../java/io/FileSystem.java` | normalize, prefixLength, resolve, attrs, list, … |
| `DefaultFileSystem` | same package | **Hard-wired** `return new UnixFileSystem();` |
| `UnixFileSystem` | same package | Separators from props; Unix absolute = leading `/` |
| `WinNTFileSystem` | **absent** | Not in Android ojluni tree |
| Natives | `UnixFileSystem_md.c` | canonicalize, attributes, list, mkdir, … |

Android-specific: several methods call **`Libcore.os`** instead of pure JNI:

- `checkAccess` → `Libcore.os.access`
- `getLength` → `Libcore.os.stat`
- `delete` → `Libcore.os.remove`
- `rename` → `Libcore.os.rename`

Others remain JNI (`getBooleanAttributes0`, `list0`, `createDirectory0`, `canonicalize0`, …).

`File` already knows separators can differ: URI construction uses `fs.fromURIPath` and, if `separatorChar != '/'`, replaces `/` → separator. That is the OpenJDK hook Win32 relies on — but **only if** `DefaultFileSystem` returns a Windows `FileSystem`.

### 2.2 Layer B — IoBridge / Os

| Artifact | Role |
|----------|------|
| `IoBridge.open/read/write` | Used by `FileInputStream` / `FileOutputStream` (Android-changed) |
| `Libcore.os` / `libcore.io.Linux` | ~136 native methods; file subset: open, read, write, close, stat, lstat, fstat, access, mkdir, rename, remove, unlink, readlink, realpath, mmap, … |
| `DexPathList.splitPaths` | `path.split(File.pathSeparator)` then `Libcore.os.stat` for directory filter; `new File(path)` for elements |

Phase 2 PE stubs only covered a **tiny** slice (e.g. `writeBytes`, partial `UnixFileSystem` attrs, relative paths).

### 2.3 Layer C — ART C++

| Artifact | Role |
|----------|------|
| `OS::OpenFileForReading` / `OpenFileWithFlags` | `vendor/art/libartbase/base/os_linux.cc` (name is historical; has some `_WIN32` bits) |
| `ZipArchive::Open(filename)` | boot.jar / app jars via native zip |
| `MemMap::MapFile*` | map jar/dex/oat regions (`mem_map_windows.cc` exists for Win) |
| `FdFile` | fd-centric file wrapper |
| Classpath splitting | **`Split(..., ':')`** in `runtime.cc` / options — **not** `File.pathSeparator` |

ART native open does **not** go through `java.io.FileSystem`. Mixed-path support for `-Xbootclasspath:C:\a/b.jar` is a **layer C** (and string split) problem as well as layer A/B.

### 2.4 Classpath list separator vs file separator

| Mechanism | Separator today |
|-----------|-----------------|
| ART `-cp` / `-Xbootclasspath` parsing | **`:`** hardcoded today (`ParseStringList<':'>`, `Split(..., ':')`) — **must become `;` on Win64** |
| `DexPathList` / `PathClassLoader` | `File.pathSeparator` (Unix today → `:`; **WinNT-class → `;`**) |
| Path inside one element | `/` and/or `\` after normalize |

**Product rule (Win64):** list separator is **`;`**. See §1.5. Do not use `:` for multi-jar lists on Windows.

---

## 3. How libcore *uses* filesystem/path APIs

### 3.1 High-traffic call graph (file I/O)

```text
FileInputStream.<init>(path)
  → IoBridge.open(path, O_RDONLY)
      → Libcore.os.open(path, flags, 0666)
      → fstat to reject directories

FileInputStream.read
  → IoBridge.read(fd, …)
      → Libcore.os.read

FileOutputStream.write
  → IoBridge.write(fd, …)
      → Libcore.os.write

File.exists / isFile / isDirectory
  → FileSystem.getBooleanAttributes
      → UnixFileSystem.getBooleanAttributes0 (JNI)  [or WinNT equivalent]

File.length
  → UnixFileSystem.getLength → Libcore.os.stat   [Android]

PathClassLoader / DexPathList
  → split(File.pathSeparator)
  → File + optional Libcore.os.stat
  → DexFile open (native ART zip/dex) using path string
```

### 3.2 Who needs mixed paths

| Consumer | Needs mixed `\`+`/` | Needs drive absolute | Notes |
|----------|---------------------|----------------------|--------|
| `File` path math | **Yes** | **Yes** | Product mandate |
| `IoBridge`/`Linux.open` | **Yes** (pass-through + normalize) | **Yes** | Win32 API can open mixed if UTF-16 path correct |
| `DexPathList` | **Yes** | **Yes** | Uses `File` + `stat` |
| Charset / jar URL handlers | Medium | Medium | `ClassPathURLStreamHandler` uses `File`→URI; entry names stay `/` |
| ICU data path props | Medium | Medium | Often absolute install paths on Windows |

### 3.3 NIO.2 (`java.nio.file`) — **non-goal for now**

This tree: `DefaultFileSystemProvider` → **`LinuxFileSystemProvider`**.  
OpenJDK Windows: `WindowsFileSystemProvider` / `WindowsPath` / native dispatcher (not adopted).

**Decision:** A full Windows `sun.nio.fs` stack is **out of scope** for the current Phase 3 filesystem plan.  
`java.io.File` + Os/IoBridge + ART open cover class loading and classic I/O.  
If code hits NIO paths, leave Linux-shaped stubs or fail clearly until a later explicit product milestone reopens this.

---

## 4. How libart uses paths

### 4.1 Boot and app code paths

1. Parse `-Xbootclasspath` / `-cp` → vector of **filename strings** (`:`-split).  
2. `ZipArchive::Open` / dex loader maps each jar/dex.  
3. Imageless Hello today: `run/boot.jar`, `run/hello.jar` (relative, `/`-only) — works under wine without Win path semantics.

### 4.2 Path assumptions in ART sources

- Many utilities concatenate with **`/`** (`file_utils.cc`, image paths, dalvik-cache naming).  
- Host/test code assumes POSIX paths.  
- `OS::OpenFileWithFlags` ultimately needs a pathname the **Windows CRT or Win32** understands.

For product Win64:

- Layer C should accept the same mixed/drive paths as layer B (shared normalize helper recommended).  
- Prefer not to invent a fourth path language for ART-only code.

### 4.3 `kIsTargetWindows`

`globals.h` already has `ART_TARGET_WINDOWS` / `kIsTargetWindows`. Use that for path helpers and OS open, not ad-hoc `#ifdef _WIN32` only in random leaves.

---

## 5. OpenJDK / ojluni reuse

### 5.1 Available upstream (not in this tree)

OpenJDK `src/java.base/windows/`:

| Component | Purpose |
|-----------|---------|
| `java.io.WinNTFileSystem` | Path syntax, attrs, list, canonicalize |
| `WinNTFileSystem_md.c` | Win32 natives |
| `java.io.DefaultFileSystem` (windows) | `new WinNTFileSystem()` |
| `sun.nio.fs.Windows*` | NIO.2 Windows stack |

License: OpenJDK Classpath exception (same family as ojluni). Expect re-fit for Android: BlockGuard, `Libcore.os` redirects, hiddenapi, no module layout.

### 5.2 What **not** to expect from AOSP libcore

No Windows `java.io` FileSystem in vendored Android-16-era libcore. Searching the tree finds only `UnixFileSystem` + Linux NIO providers.

### 5.3 Reuse strategy

| Piece | Reuse? | Effort |
|-------|--------|--------|
| WinNT path math (normalize, prefix, absolute, resolve) | **Yes — primary** | Medium (port + Android hooks) |
| WinNT JNI list/attrs/canon | **Yes** | Medium |
| NIO Windows provider | **Non-goal for now** | High only if reopened |
| Android `Libcore.os` file ops | **Implement** with Win32 (no OpenJDK twin) | High (breadth) |
| ART `OS::Open*` | Project Win32 path (may share normalize) | Medium |

---

## 6. Options (filesystem-focused)

### Selected: **Option H — Hybrid** (locked)

**Adopted** for Win64 ART path/filesystem work:

1. **Layer A:** WinNT-class `java.io.FileSystem` (port OpenJDK `WinNTFileSystem` lineage or faithful equivalent).  
2. **Layer B:** `Linux`/`Os` PE natives with **shared path normalize** (UTF-16, slash unify) before Win32 calls.  
3. **Layer C:** Same normalize in `OS::Open*` / zip open.  
4. **List separator:** **`;`** on Win64 (`path.separator` + ART `ParseStringList` / `Split`). Linux keeps `:`. No dual-accept for v1.  
5. **NIO.2 Windows provider:** **non-goal for now** (§3.3 / §8.2).  
6. **Phase-2 Unix stubs:** Keep only until WinNT-class + Os open land; then delete.

### Option U — permanent `UnixFileSystem` — **rejected** as product end state

Bootstrap-only; fails mixed/drive path mandate.

### Option W — WinNT layer A alone — **insufficient** as full plan

Correct for path *syntax*, but streams (IoBridge/Os) and ART jar open still need the hybrid B/C work in Option H.

```text
                    ┌──────────────────────────┐
   path string ───► │ normalize_win_path()     │  shared C++/JNI helper
                    │  · accept \ and / mixed  │
                    │  · drive / UNC rules     │
                    │  · UTF-8 ↔ UTF-16        │
                    └────────────┬─────────────┘
           ┌─────────────────────┼─────────────────────┐
           ▼                     ▼                     ▼
    WinNT FileSystem        Os open/stat          OS::Open / Zip
    (Java syntax)           (IoBridge)            (ART C++)
```

---

## 7. Feasibility rating

| Topic | Rating | Notes |
|-------|--------|-------|
| Mixed path mandate | **Required** | Product / win32_port §4.7.1 |
| Layer A WinNT-class | **Feasible** | OpenJDK source exists; Android refit needed |
| Layer B Os file ops | **Feasible, large** | Breadth (~file subset of 136 natives), not path math |
| Layer C ART open | **Feasible** | Smaller surface; share normalize |
| Keep UnixFileSystem as product | **Not feasible** under mixed-path mandate |
| NIO Windows provider | **Non-goal for now** | Reopen only with explicit product need |
| Classpath `:` with drive letters | **Fragile** | Design around relative multi-jar + careful absolute handling |
| Overall FS for Phase 3 start | **Go** | Separate track from ICU/crypto; critical path for A4 |

**Calendar sketch (filesystem track only, one engineer):**

| Slice | Rough effort |
|-------|----------------|
| Shared normalize + wide-path open | 1–2 weeks |
| WinNT-class Java + JNI attrs/list/canon | 2–4 weeks |
| Os open/read/write/close/stat/access/… for streams | 4–8 weeks |
| ART OS::Open + zip path parity tests | 1–2 weeks |
| NIO Windows | **Deferred / non-goal** (not scheduled) |

(Does not include full Phase 3 non-file natives.)

---

## 8. Acceptance cases (filesystem)

### 8.1 Must pass (Phase 3a / A4-oriented)

| ID | Input | Expect |
|----|--------|--------|
| P1 | `run/hello.jar` relative | open, PathClassLoader, Hello |
| P2 | `C:/abs/hello.jar` | absolute File; open; load |
| P3 | `C:\abs\hello.jar` | absolute File; open; load |
| P4 | **`C:\abs/mixed/hello.jar`** | absolute; open; load |
| P5 | `File("C:\\a\\b").getParent()` / `getName()` | Windows-correct components |
| P5b | cwd `C:\work`, `File("..\\file.txt").getAbsolutePath()` | `C:\file.txt` form (or `C:\work\..\file.txt` then canon → `C:\file.txt`); **not** `/file.txt`, **not** `//?/C:/…` |
| P5c | `File("rel/path/x").getAbsolutePath()` | `C:\…\rel\path\x` (sep `\` in product FileSystem) |
| P6 | `exists` / `isFile` / `length` on P2–P4 | correct |
| P7 | `FileInputStream` / `FileOutputStream` round-trip | via IoBridge/Os |
| P8 | ART `ZipArchive::Open` on P2–P4 | boot or app jar |
| P9 | `-cp run/a.jar;run/b.jar` | multi-element list with **`;`** |
| P9b | `-cp C:\\a.jar;C:\\b.jar` | two absolute Windows jars |
| P9c | `-cp C:\\a.jar:C:\\b.jar` | **must not** silently work as two jars (invalid/wrong split) |

### 8.2 Explicit non-goals (current plan)

- **Windows NIO.2** (`sun.nio.fs.WindowsFileSystemProvider` / `WindowsPath` / native dispatcher) — **non-goal for now.**  
  Not a Phase 3 FS deliverable; do not schedule unless product reopens it.  
- Every `Linux` socket/epoll method (network is a separate track).  
- Keeping `path.separator=:` on Win64; naïve classpath `Split` on `:`.  
- Wine-only validation as product sign-off (wine = agent01 gate; host Windows for drive/UNC confidence).  
- Permanent `UnixFileSystem` product façade (Option U rejected).

## 9. Recommended Phase 3 sequencing (FS only)

1. **Spec freeze:** this doc + win32_port §4.7.1 (mixed mandatory, **`;` list separator** on Win64).  
2. **Shared `normalize_win_path`** (C++), unit-tested for P1–P5 strings.  
3. **Layer B open/stat/read/write/close** on PE (unblocks streams even before full FileSystem math).  
4. **Layer A WinNT-class FileSystem** + `DefaultFileSystem` switch on `ART_TARGET_WINDOWS`.  
5. **Layer C** call normalize in `OS::Open*` / zip.  
6. Golden tests P1–P9 under wine64; subset on real Windows.  
7. Retire Phase-2 Unix path stubs.  
8. **Stop on NIO.** Windows NIO is not a scheduled follow-on unless product explicitly reopens it.

---

## 10. Risks

| Risk | Mitigation |
|------|------------|
| Drive letter vs classpath list sep | **Use `;` on Win64**; change ART parsers; do not split on `:` |
| UTF-8 vs UTF-16 Windows paths | Always wide APIs (`*W`); convert at boundary |
| Android BlockGuard / hiddenapi | Keep Java wrappers; only replace FileSystem impl + natives |
| Dual maintenance Unix + Win FileSystem | Nested `vendor/libcore` ojluni + `multiplatform/windows` mirrors |
| Wine path quirks vs real NT | Host Windows smoke for P2–P4 |
| Growing PE stub DLL forever | Replace with real `libjavacore` / Os natives early in 3a |

---

## 11. Conclusion

- **Decision locked: Option H — Hybrid.**  
- Layers: path syntax (A), Os I/O (B), ART open (C), shared normalize.  
- Mixed/hybrid paths mandatory → WinNT-class layer A (not permanent `UnixFileSystem`).  
- Absolute resolution → normal Win32 `C:\…` (not POSIX `/…`, not `\\?\` by default); fix ART/libcore if `\` breaks them.  
- **`path.separator=;` on Win64**; ART boot/classpath parsers must match.  
- Reuse OpenJDK `WinNTFileSystem` for syntax/attrs; implement `Libcore.os` file ops with Win32; share normalize with ART `OS::Open*`.  
- **Windows NIO.2 provider: non-goal for now.**  
- **Feasibility: Go** — early Phase 3 FS track feeding A4.

## 12. References (in-tree)

- [win32_port.md](win32_port.md) — overall port; §4.7 / §4.7.1 path mandate  
- `vendor/libcore/ojluni/src/main/java/java/io/{File,FileSystem,DefaultFileSystem,UnixFileSystem}.java`  
- `vendor/libcore/ojluni/src/main/native/UnixFileSystem_md.c`  
- `vendor/libcore/luni/src/main/java/libcore/io/{IoBridge,Linux,Libcore}.java`  
- `vendor/libcore/dalvik/src/main/java/dalvik/system/DexPathList.java`  
- `vendor/art/libartbase/base/os_linux.cc`, `os.h`, `zip_archive.cc`, `mem_map*.cc`  
- `vendor/art/runtime/parsed_options.cc`, `runtime.cc` (`Split` classpath)  
- OpenJDK (external): `src/java.base/windows/classes/java/io/WinNTFileSystem.java`  
- Phase-2 stubs: `tools/win64/jni_stubs/` (bootstrap only)

---

*Rev 5 — Option H path gates under wine; ASCII drive letters; Windows NIO.2 non-goal for now.*


## Appendix — ICU drive-letter pitfall (Phase 3 evidence)

On imageless Win64 ART, unicode property natives are not fully wired:

```text
Character.isLetter('C') == false
Character.isLetter('c') == false
```

Any `WinNTFileSystem` port that copies OpenJDK’s `Character.isLetter(c)` drive check will leave:

```text
new File("C:\\x").getPath() == "C:\\x"   // normalize OK
prefixLength == 0
isAbsolute == false
getAbsolutePath() == user.dir + "\\C:\\x"  // wrong join
```

**Required pattern:**

```java
private static boolean isDriveLetter(char c) {
    return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z');
}
```

Gate: `tools/verify/win64_phase3/run_probe.sh` asserts drive/mixed/UNC absolute + multi-jar `;`.

*Rev 5 — Option H path gates; ASCII drive letters; Windows NIO still non-goal.*
