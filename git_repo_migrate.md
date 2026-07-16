# Plan: migrate to `dalvikvm-multiplatform` (branch + nested repos)

**Type:** Plan only (feasibility / conflict analysis)  
**Date:** 2026-07-16  
**Source tree:** `/home/agent/Projects/dalvikvm-linux`  
**Target tree:** `/home/agent/Projects/dalvikvm-multiplatform`  
**Goal:** Stop relying on ignored dirty `vendor/` + patch/overlay as source of truth; use **`artmp_*` branches** on nested AOSP-derived repos; main records nested commit SHAs and publishes `.gitmodules` for recursive clone UX.

**Product clone guarantee (locked):**  
One command —

```bash
git clone --recursive git@github.com:sulfatelab/dalvikvm-multiplatform.git
```

— must yield **everything required to build and test ART for GNU/Linux and Windows** (all nested source repos: ART, libcore, ICU, BoringSSL/OpenSSL stack deps, libbase, ziparchive, unwind, etc.). No second manual hunt for MinDalvikVM-Archive trees. Host toolchains (system Clang/apt packages, optional Wine for Linux-hosted PE gates, Windows SDK via documented env such as win64-dev-env/xwin) may still be installed on the machine, but **all project-controlled source dependencies ship as nested repos under main**.

---

## Snapshot of starting state

| Location | State |
|----------|--------|
| `dalvikvm-multiplatform` | Empty repo, **no commits**, only `.git` |
| `dalvikvm-linux` | Active product; `origin` = `cinit/dalvikvm-linux`; **local main ahead of origin** |
| `dalvikvm-linux/vendor/art` | Detached `android-16.0.0_r4` (`1690c69`), **dirty** (~49 files, ~+1797/−167), shallow |
| `dalvikvm-linux/vendor/libcore` | Detached `android-16.0.0_r4` (`1c599b6`), **clean** |
| `vendor/` in product | **gitignored** — not recorded as gitlinks today |
| Port “overlay” | Split: **in-tree ART dirt** + product `compat/` + `archive-patches/` + PE stubs |

---

## Overall verdict

| Question | Answer |
|----------|--------|
| Is the plan workable? | **Yes** |
| Biggest risk | Treating “copy nested repo” + `.gitmodules` without a clear **path layout**, **complete nested inventory (ICU/SSL/…)**, and **what “de-overlay” means** |
| Best order | Slightly reorder the user steps (see below) |
| Execute now? | Only when explicitly approved |

**Verdict: Go, with a clear migration design.**  
The model (named `artmp_*` branches on nested AOSP-derived repos + main repo recording gitlinks + `.gitmodules` for clone UX) is standard Git and fits this project better than “ignored dirty `vendor/` + `archive-patches/`.”

---

## Target model (agreed direction)

1. **Git branches** for AOSP-touching changes (not patch-file primary workflow).  
2. Branch naming: base tag `android-16.0.0_r4` → product branch **`artmp_android-16.0.0_r4`**.  
3. Nested full git repos under main (e.g. `vendor/art`, `vendor/libcore`) — **local nested repos**, not `git submodule add` from AOSP.  
4. Main records nested **commit SHAs** (gitlinks) and has **`.gitmodules`** so `git clone --recursive` works for others (submodule protocol).  
5. Remotes (later):  
   - Main: `git@github.com:sulfatelab/dalvikvm-multiplatform.git`  
   - Nested: `git@github.com:sulfatelab/dalvikvm-multiplatform_art.git`, `_libcore`, etc.  
6. **You** create GitHub repos and push with SSH agent.  
7. **Codex** (when asked) sets remotes/upstreams only; does not push unless directed.

### Nested vs submodule (explicit)

| Aspect | Reality |
|--------|---------|
| Local day-to-day | Full nested repositories you commit/push independently |
| After main gitlink + `.gitmodules` | Consumers with `--recursive` get them **as submodules** |
| Conclusion | Duality is normal Git; not a contradiction |

---

## Scope decisions (locked / remaining)

1. **Nested set:** **full** — all repos needed for GNU/Linux + Windows ART build/test.  
   - Includes ART, libcore, ICU, BoringSSL, libbase, nativehelper, logging, ziparchive, unwinding, lzma, and other AOSP externals listed below.  
   - Recursive clone must be complete.

2. **`compat/windows/art` → nested ART `artmp_*`:** **LOCKED fold in.**  
   - Sources such as `runtime_windows.cc`, `thread_windows.cc`, `monitor_windows.cc`, `sigchain_windows.cc`, `openjdkjvm_memory_windows.cc`, related stubs become part of the **nested `vendor/art` tree** on `artmp_android-16.0.0_r4` (placed under appropriate ART paths / build wiring in that commit series).  
   - After fold, main must **not** keep a parallel `compat/windows/art` overlay as source of truth.

3. **`compat/windows/libcore` → nested libcore `artmp_*`:** **LOCKED fold in.**  
   - e.g. `WinNTFileSystem.java`, `DefaultFileSystem.java`, `AndroidHardcodedSystemProperties.java` (and any further Windows libcore Java) land in nested **`vendor/libcore`** on the same `artmp_*` branch policy.  
   - Boot.jar / product scripts consume nested libcore (+ build wiring), not a main-repo Java overlay tree.

4. **`compat/include`:** **LOCKED keep in main.**  
   - POSIX/Win prelude headers and shims stay product-owned under main `compat/include/` (and related product-only bits such as `compat/src` stubs if still needed for PE).  
   - Not folded into AOSP nested trees.

5. **Other `compat/` (not art/libcore trees):** keep in main unless later decided otherwise — e.g. `compat/java-stubs`, `compat/openjdk_inc`, `compat/src`.

6. **Leave `dalvikvm-linux` alone as fallback?**  
   - **Recommend yes** until multiplatform clone + gates are proven.

7. **Branch name:** `artmp_android-16.0.0_r4`.

8. **Main default branch:** `main`.

---

## What “de-overlay / de-patch” means (and does not)

**Means:** no silent dirty vendor trees; no patch-file workflow as primary source of truth for AOSP trees.

**Does not mean:** delete product PE stubs or **`compat/include`**.  
**Does mean:** fold **`compat/windows/art`** and **`compat/windows/libcore`** into nested artmp branches (locked).

| Current change location | Destination | Why |
|-------------------------|-------------|-----|
| Dirty files under `vendor/art` | Nested **art** `artmp_*` | Primary de-patch target |
| `archive-patches/*` | Nested commits + docs | History on `artmp_*`; notes only in main |
| `compat/windows/art/*` | Nested **art** `artmp_*` (**locked fold**) | Windows runtime spine owned with ART multipath branch |
| `compat/windows/libcore/*` | Nested **libcore** `artmp_*` (**locked fold**) | WinNT FS / properties owned with libcore multipath branch |
| `compat/include/*` | **Main** (**locked keep**) | Toolchain/POSIX shims for multiplatform product build |
| `compat/src`, `java-stubs`, `openjdk_inc` | **Main** (default) | Product-only glue unless later absorbed |
| PE `tools/win64/jni_stubs/*` | **Main** | PE stand-ins, not AOSP modules |
| `tools/`, `overlay/`, verify gates, docs | **Main** | Multiplatform product |

---

## Branch naming

```text
upstream tag/commit   android-16.0.0_r4   (pin full SHA too)
product branch        artmp_android-16.0.0_r4
optional topic        artmp_android-16.0.0_r4_<topic>  (merge into artmp_*)
```

Same branch name on each nested repo aids the mental model. Document **base pin** (tag + full SHA) in main README.

---

## User steps vs recommended order

### User-proposed steps

1. De-overlay/de-patch: make changes in nested repos  
2. Create `artmp_*` branches and commit  
3. `cp -r` nested repos into `dalvikvm-multiplatform` (copy repo, not submodule add)  
4. Copy docs and scripts from `../dalvikvm-linux`  
5. Add `.gitmodules` for main  
6. Commit main repo  
7. You setup GitHub; Codex sets upstream remotes  
8. You `git push` with SSH agent  

### Recommended execution order (adjusted)

```text
0. Freeze scope: **full nested dependency set** (see inventory) — recursive clone = complete source tree for Linux+Windows ART
1. Inventory deltas for every nested repo that is dirty (art heavy; system deps light)
2. Prepare nested workspaces (copy-aside OR in-place); unshallow where needed
3. For each nested repo: branch `artmp_android-16.0.0_r4` (or agreed pin base), commit product deltas
4. **Fold** `compat/windows/art` → nested art `artmp_*`; **fold** `compat/windows/libcore` → nested libcore `artmp_*`
5. `cp -a` **all** nested repos into `dalvikvm-multiplatform/vendor/...` (preserve layout map)
6. Copy product docs/scripts/**`compat/include`** (+ remaining non-folded compat)/tools/overlay (exclude build trash; **omit** folded windows art/libcore overlays)
7. Write `.gitmodules` entries for **every** nested path + README clone/build matrix
8. Main: git add product + all gitlinks; first commit(s)
9. You create GitHub repos (main + one per nested name)
10. Codex: set remotes/upstreams (when asked)
11. You: push **all nested**, then main
12. Smoke: `clone --recursive` on clean machine + Linux e2e + Win64 package/wine gates
```

---

## Step-by-step feasibility and conflicts

### Step 1 — De-overlay / de-patch into nested repos

**Feasible.** Primary work: turn **dirty `vendor/art`** into intentional commits.

**Fold procedure (locked):**

1. **ART:** apply dirty `vendor/art` + copy/integrate `compat/windows/art/*` into nested art tree (paths + Android.bp/CMake/`port_policy` so Windows sources build). Commit on `artmp_android-16.0.0_r4`.  
2. **libcore:** import `compat/windows/libcore/**` into nested libcore (ojluni/java layout as appropriate), commit on `artmp_android-16.0.0_r4`.  
3. **Main product:** remove folded trees from main `compat/windows/{art,libcore}` after nest commits exist; keep **`compat/include`** (and non-folded compat pieces).  
4. Update product build scripts that referenced `compat/windows/art` or `compat/windows/libcore` to use nested `vendor/art` / `vendor/libcore` paths.

**libcore note:** vendor libcore is currently clean; Windows Java lives under product `compat/windows/libcore` until folded in step above.

### Step 2 — Create `artmp_*` and commit

**High feasibility.**

```bash
# conceptual — do not run until execute phase
cd vendor/art   # or copy-aside worktree
# unshallow if needed
git switch -c artmp_android-16.0.0_r4   # from android-16.0.0_r4 / 1690c69
# stage intentional deltas only
git commit -m "artmp: Win64/multiplatform deltas on android-16.0.0_r4"
```

**Conflict:** committing inside `dalvikvm-linux/vendor/*` mutates the live build tree.  

**Mitigations:**

- **A (safer):** work on a copy, then place into multiplatform  
- **B (simpler):** branch/commit in place, then `cp -a` whole tree  

**Recommend A** if `dalvikvm-linux` must remain a recoverable fallback.

### Step 3 — Copy nested repos into multiplatform

**Feasible.** Use **`cp -a`** so `.git` and modes are preserved. Do **not** use `git submodule add` for this step.

Suggested layout:

```text
dalvikvm-multiplatform/
  vendor/art/          # nested git @ artmp_android-16.0.0_r4
  vendor/libcore/      # nested git
  compat/
  tools/
  overlay/
  *.md
  .gitmodules
  .gitignore
  README.md
```

| Concern | Detail |
|---------|--------|
| Size | `art` ~125M, `libcore` ~136M — fine for local copy |
| Nested remotes after copy | Still googlesource until step 7 |
| Build graph | Full build may still need MinDalvikVM-Archive / win64-dev-env for system deps |


### Step 4 — Copy docs and scripts from dalvikvm-linux

**Feasible** with an explicit include list.

**Copy (yes)**

- Docs: `win32_port.md`, `filesystem_win32.md`, `project_scope.md`, `archive-patches/` (historical notes), this plan  
- Product: `compat/include/` (**keep**), other non-folded `compat/*` if any, `overlay/`, `tools/` (bp2cmake, bootjar, win64, verify), useful `native/` recipes  
- **Do not** keep `compat/windows/art` or `compat/windows/libcore` as long-term main overlays after fold (sources live in nested artmp)  
- New `.gitignore` that does **not** blanket-ignore nested vendor pins  

**Do not copy**

- `build/`, `dist/`, `.pytest_cache/`, PE `*.obj`/`*.dll`, `tools/verify/**/bin`, phase1 log forests  
- Machine-local secrets / hardcoded throwaway paths  

**Conflict:** uncommitted product dirt on `dalvikvm-linux` (e.g. bp2cmake WIP, untracked headers). Decide: copy working tree selectively vs only committed tree.

**After copy:** grep for hardcoded `/home/agent/Projects/dalvikvm-linux` and fix paths if needed.

### Step 5 — Add `.gitmodules`

**Feasible** after nested paths exist at the commits to pin.

Example (URLs final when GitHub exists):

```gitconfig
[submodule "vendor/art"]
    path = vendor/art
    url = git@github.com:sulfatelab/dalvikvm-multiplatform_art.git
[submodule "vendor/libcore"]
    path = vendor/libcore
    url = git@github.com:sulfatelab/dalvikvm-multiplatform_libcore.git
```

Nested already having `.git` is fine: main `git add vendor/art` records a **gitlink** (mode `160000`), not file contents.

### Step 6 — Commit main repo

First main commit(s) should include:

1. Product docs/tools/compat/overlay  
2. `.gitmodules`  
3. Gitlinks for nested paths at **artmp HEADs**  
4. README: recursive clone, branch policy, base pin SHAs  
5. `.gitignore`: ignore `build/`, `dist/`, bins — **not** `vendor/art` / `vendor/libcore`  

**Hard rule:** nested trees must be **clean** on `artmp_*` before main records gitlinks.

### Step 7 — GitHub + remotes

| Actor | Action |
|-------|--------|
| You | Create `dalvikvm-multiplatform`, `_art`, `_libcore`, … |
| Codex (when asked) | Set SSH remotes on main + nested; optional upstream tracking |
| You | Push with SSH agent |

**Recommend nested remotes:** keep googlesource as `upstream`, sulfatelab as `origin` (or `sulfate`).

### Step 8 — Push order

1. Nested repos: push `artmp_android-16.0.0_r4` (and tags if any)  
2. Main: push `main` with matching gitlinks  

---

## `.gitignore` policy change (critical)

Today (`dalvikvm-linux`):

```text
vendor/
```

That **must not** be carried over unchanged for pinned nested paths. Multiplatform should ignore build outputs only, e.g.:

```text
/build/
/out/
/dist/
**/bin/
*.obj
*.dll
*.exe
# etc.
# Do NOT ignore vendor/art or vendor/libcore if they are gitlink pins
```

---

## Shallow clone caveat

`vendor/art` and `vendor/libcore` currently look **shallow**. Before first push to GitHub:

- `git fetch --unshallow` (or full re-clone from AOSP tag), then branch/commit/push  

Otherwise collaborators may get incomplete history.

---


---

## Full nested repository inventory (recursive clone must include all)

**Policy (locked by product):** main is the single entrypoint. After `git clone --recursive`, the developer has **all project source dependencies** to build and test ART on **GNU/Linux and Windows**. That includes ART, libcore, **ICU**, **BoringSSL (ssl)**, and the rest of the system/external graph — not art+libcore alone.

### Naming convention (GitHub)

```text
main:    sulfatelab/dalvikvm-multiplatform
nested:  sulfatelab/dalvikvm-multiplatform_<name>
```

Examples: `_art`, `_libcore`, `_libbase`, `_libnativehelper`, `_logging`, `_libziparchive`, `_libprocinfo`, `_unwinding`, `_lzma`, `_boringssl`, `_icu`, `_fmtlib`, `_cpu_features`, `_dlmalloc`, `_tinyxml2`, `_oj-libjdwp`, `_bouncycastle`, `_conscrypt`, `_okhttp`, `_fdlibm`, …

Use short stable `<name>` tokens (match directory names). Document the map in main README.

### Suggested tree under main

```text
dalvikvm-multiplatform/
  vendor/
    art/                 # android-16 pin + artmp_*  (active ART)
    libcore/             # android-16 pin + artmp_*
    libbase/
    libnativehelper/
    libprocinfo/
    libziparchive/
    logging/             # provides liblog
    unwinding/           # provides libunwindstack
    external/
      boringssl/         # SSL/crypto
      lzma/
      cpu_features/
      dlmalloc/
      tinyxml2/
      oj-libjdwp/
      fmtlib/            # or vendor/fmtlib
    icu/                 # libicuuc / libicui18n / related
    # java externals if required by boot/libcore build:
    bouncycastle/
    conscrypt/
    okhttp/
    fdlibm/
  compat/ tools/ overlay/ docs ...
  .gitmodules
```

Exact paths can mirror MinDalvikVM-Archive layout under `vendor/` to minimize script churn.

### Source of copy (today on agent01)

| Nested name | Current local source (copy-aside) | Typical libs |
|-------------|-------------------------------------|--------------|
| art | `dalvikvm-linux/vendor/art` (**prefer android-16**) | libart, libartbase, libdexfile, libart-compiler, libartpalette, libopenjdkjvm, libprofile, libsigchain, libnativebridge, libnativeloader, … |
| libcore | `dalvikvm-linux/vendor/libcore` (**prefer android-16**) | libjavacore, libopenjdk, libandroidio, libicu_jni, … |
| libbase | `MinDalvikVM-Archive/native/libbase` | libbase |
| libnativehelper | `…/native/libnativehelper` | libnativehelper |
| libprocinfo | `…/native/libprocinfo` | libprocinfo |
| libziparchive | `…/native/libziparchive` | libziparchive |
| logging | `…/native/logging` | liblog |
| unwinding | `…/native/unwinding` | libunwindstack |
| lzma | `…/native/external/lzma` | liblzma |
| boringssl | `…/native/external/boringssl` | crypto/ssl used by conscrypt/openjdk |
| cpu_features | `…/native/external/cpu_features` | cpu_features |
| dlmalloc | `…/native/external/dlmalloc` | dlmalloc |
| tinyxml2 | `…/native/external/tinyxml2` | tinyxml2 |
| oj-libjdwp | `…/native/external/oj-libjdwp` | JDWP |
| fmtlib | `…/native/fmtlib` | fmt |
| icu | `…/javalib/external/icu` | libicuuc, libicui18n, libicu* |
| bouncycastle / conscrypt / okhttp / fdlibm | `…/javalib/external/*` | Java/crypto support as needed by boot |

**ART pin conflict to resolve at execute time:**  
- Active port ART/libcore = **android-16** under `dalvikvm-linux/vendor/*`.  
- Archive ART = older pin under `MinDalvikVM-Archive/native/art`.  
**Use android-16 art+libcore as nested truth.** System deps currently at older archive pins may stay on those SHAs initially **or** be retargeted later; either way they **must live under multiplatform** as nested repos.

### Branch policy on every nested repo

```text
base pin:   documented tag/SHA (android-16 for art/libcore; current archive pin for others until upgraded)
branch:     artmp_android-16.0.0_r4
```

Even “clean” deps get the branch (or a pin branch with zero delta) so remotes and clone instructions are uniform. Product edits only where needed.

### What recursive clone does *not* have to vendor

These are **host/toolchain** (document in README), not nested AOSP git:

- System packages: CMake, Ninja, Clang/LLD, Java, Python, Wine (optional Linux PE gates)
- Windows cross kit: e.g. `win64-dev-env` / xwin SDK headers+libs, libc++ for Windows (may remain a documented bootstrap script that downloads/builds into a local env dir, **or** optionally a separate tool repo later)
- Build output dirs (`build/`, `dist/`)

If the project later wants zero external bootstrap, that is a **follow-on** (toolchain bootstrap repo); it is not required to satisfy “all AOSP/source deps in recursive clone.”

### `.gitmodules` scale

Expect **~15–20** submodule entries for a complete graph (not 2). Generation checklist:

1. Every path under `vendor/` that contains a nested `.git`  
2. URL `git@github.com:sulfatelab/dalvikvm-multiplatform_<name>.git`  
3. Main gitlink SHA = that nested repo’s `artmp_*` HEAD  
4. CI or script: fail if any inventory path missing after recursive clone  

### Copy / commit volume

| Work | Scale |
|------|--------|
| Nested copies | Hundreds of MB to a few GB depending on ICU/boringssl history + shallow vs full |
| Nested GitHub repos | One remote per nested name (~15–20) |
| First push | Push **all nested** before main so recursive clone resolves |

---

## Success criteria (migration “done” before push)

- [ ] **All** inventory nested repos present under multiplatform with `artmp_*` (or agreed) branches, clean HEADs  
- [ ] Nested `art` includes former dirty deltas **and** folded `compat/windows/art`  
- [ ] Nested `libcore` includes folded `compat/windows/libcore`  
- [ ] Main retains **`compat/include`**; no parallel windows art/libcore overlay as source of truth  
- [ ] ICU, BoringSSL, libbase, logging, ziparchive, unwinding, lzma, and other inventory deps are nested (not left only in MinDalvikVM-Archive)  
- [ ] Multiplatform main has commit(s) with product tree + **gitlinks for every nested path** + complete `.gitmodules`  
- [ ] README states: `git clone --recursive` → full Linux+Windows ART source graph  
- [ ] No reliance on `archive-patches` as **apply steps** for ART (docs only)  
- [ ] Ready for you to push **all nested**, then main, when GitHub + SSH ready  
- [ ] Optional smoke: fresh recursive clone configures/builds on Linux and produces Win64 PE package  

---

## Risk register

| Risk | Severity | Mitigation |
|------|----------|------------|
| Commit incomplete dirty ART | High | Review status/diff; map archive-patches into commits |
| Shallow push fails | Medium | Unshallow before first nested push |
| Main still ignores `vendor/` | High | New gitignore policy |
| `cp -r` without `-a` loses `.git`/modes | High | Use `cp -a` |
| `.gitmodules` URL mismatch | Medium | Match exact GitHub repo names |
| Scripts hardcode old paths | Medium | Grep/fix after copy |
| Miss a dep in `.gitmodules` so recursive clone is incomplete | High | Checklist against inventory; CI “nested present” |
| Host toolchain still required (Clang, Windows SDK/xwin, Wine) | Medium | Document in README; not nested source |
| Double history linux vs multiplatform | Low | Multiplatform as successor; freeze linux after cutover |
| Folding `compat/windows/art` into ART build wiring | Medium | Commit path + CMake/bp2cmake/`port_policy` updates together |
| Leaving stale main overlays after fold | Medium | Delete/stop using `compat/windows/{art,libcore}` once nested commits land |
| Dropping `compat/include` by mistake | High | Explicit keep list in copy step |

---

## Feasibility ratings

| Proposal | Feasibility | Comment |
|----------|-------------|---------|
| Manage with **git branches** instead of patch files | **High** | Correct primary model |
| `artmp_android-16.0.0_r4` product branches | **High** | Clear, scalable |
| Nested repos + main records commit SHAs | **High** | Requires stop ignoring paths + commit first |
| `.gitmodules` so `--recursive` works | **High** | Standard; local still nested full repos |
| SSH remotes under `sulfatelab/dalvikvm-multiplatform*` | **High** | Org/repo creation is the gate |
| Eliminate **all** overlay | **Low–Medium** | Eliminate dirty/patch primary; keep product glue |
| Nest all system deps (ICU, SSL, …) in first multiplatform commit | **High / required** | Product requirement: recursive clone has everything |

---


---

## Commit identity (locked)

When creating commits (nested or main) during this migration:

| Field | Value |
|-------|--------|
| Author / committer | **global git identity** — `user.name=ACh Sulfate`, `user.email=dex@tmpfs.dev` (`git config --global`) |
| Co-author trailer | Always include when Codex authors the commit content: |

```text
Co-authored-by: Codex <codex@openai.com>
```

Do **not** override author with a different name/email unless the user explicitly says so. Prefer default `git commit` so global `user.*` applies.


## Explicit non-actions (until “execute”)

- No file copies into multiplatform  
- No commits in nested or main (unless user says execute)  
- No remote changes / pushes from Codex unless directed  
- No deletion or rewrite of `dalvikvm-linux`  

---

## Bottom line

The plan is **sound and executable**, with the **full recursive dependency set locked**.

Critical success conditions:

1. Commit current **dirty `vendor/art`** onto **`artmp_android-16.0.0_r4`**.  
2. Nest **every** build/test source dependency (ART, libcore, **ICU**, **BoringSSL**, libbase, ziparchive, unwind, logging, …) under multiplatform.  
3. **`cp -a`** nested repos (not `git submodule add` from URL for initial import).  
4. Copy product **selectively**; exclude build/dist.  
5. Main records **gitlinks for all nested paths** + complete **`.gitmodules`**.  
6. **One `git clone --recursive`** is enough to get all sources for GNU/Linux and Windows ART build/test.  
7. You create GitHub repos and push; Codex only sets remotes when asked.  
8. “No overlay” means **no dirty vendor / no patch primary**, not “delete product `compat/`.”

**Locked fold:** `compat/windows/art` + `compat/windows/libcore` → nested `artmp_*`; **`compat/include` stays in main.**

When ready to execute, say **execute**.

## Execution status (agent01)

**Date:** 2026-07-17  
**Tree:** `/home/agent/Projects/dalvikvm-multiplatform`  
**Main commit:** `0b75273` — *Initial multiplatform tree with nested artmp_* gitlinks*

| Step | Status |
|------|--------|
| Nested artmp branches + commits (incl. art/libcore fold) | Done (20 clean repos on `artmp_android-16.0.0_r4`) |
| Copy nested repos into multiplatform `vendor/` | Done |
| Copy product docs/tools/`compat/include` (omit folded windows overlays) | Done |
| `.gitmodules` for all nested paths | Done |
| README + `.gitignore` (no blanket `vendor/` ignore) | Done |
| Path rewires for folded art/libcore | Done (bootjar + win64 phase1 CMake) |
| Main first commit with 20 gitlinks | Done |
| Create GitHub repos | **You** |
| Set remotes / push | **You** (SSH); Codex only when asked |
| Smoke clone --recursive + gates | Pending after push |

**Notes**

- Nested trees remain **shallow** in places; unshallow before first nested push if full history is required.
- `vendor/r8/r8.jar` is a product prebuilt (exception in `.gitignore`), not a nested repo.
- `../dalvikvm-linux` left intact as fallback.
- Local nested working trees stay full git repos; consumers use submodule protocol via `.gitmodules`.

