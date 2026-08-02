# ART embedding result

The probe checks Windows runtime embedding and ART DSO entry boundaries. Its
only accepted selector is the exact target ID `windows-x86_64-msvc`; no Linux,
Windows AArch64, or ARM64EC applicability is inferred.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified on Windows Server 2025 x86-64 | 2026-08-01 |

The unified CMake/Ninja graph builds the probe and makes it depend on the boot
JAR plus the native ART/libcore DSO closure. The case-local Python runner uses
no shell. It copies the probe and every regular-file DLL from the declared
runtime library directories into an isolated `bin` directory, rejects
duplicate or missing required DLL basenames, and gives each repetition its own
boot JAR, ICU data, data, temporary, and crash directories. This is required
for the normal Windows DLL dependency lookup order; merely putting the source
DLL directory on `PATH` was insufficient for the embedded load boundary.

Each process verifies all of these behaviors:

- `LoadLibraryW` finds `art.dll`, `JNI_CreateJavaVM` starts the imageless
  runtime, and detach/destroy return `JNI_OK`;
- ART's vectored exception handler continues search exactly three times;
- ART's unhandled-exception filter invokes and resumes through the embedding
  application's predecessor exactly once;
- frame SEH catches one access violation while ART is active and one after the
  runtime DSO has been unloaded;
- a late filter installed by the embedding application is preserved across
  runtime teardown and is never called unexpectedly; and
- every marker and exception-handler count is exact.

The predecessor-filter check intentionally enters ART's real unhandled
exception filter. ART therefore writes exactly one minidump per successful
process before chaining to the predecessor. The runner requires that exact
count and the successful minidump marker; a missing dump, extra dump, failed
dump write, unexpected fatal marker, or wrong handler count fails the gate.
These generated binary artifacts stay below the ignored target output and are
never VCS inputs or evidence files. The aggregate JSON contains only relative
dump names and artifact basenames/hashes, never host paths.

The fresh Linux-hosted Windows cross tree completed 1,548 actions at 32 jobs,
passed its one host reviewer, and repeated as a Ninja no-op. The native
Windows tree completed the same 1,548-action graph at 16 jobs on the 16 GiB
VM. Its first runtime attempt exposed the missing regular-file DLL staging;
after that gate-only correction, W-004 passed 27/27 twice. A subsequent
full-catalog audit found that the disposable source projection still held the
pre-migration versions of 21 Win32 Unicode source files. Refreshing that exact
regular-file closure rebuilt the affected product edges. The current-source
complete catalog then passed 67/67 in 127.52 seconds, and its identical repeat
reported `ninja: no work to do` and passed 67/67 in 130.57 seconds. W-004
accounted for 41.22 and 43.74 seconds of those runs; the embedding gate itself
passed in 2.93 and 3.34 seconds.

The accepted aggregate records two completed repetitions, 22 staged runtime
DLLs, two intentional dumps, zero missing/forbidden/count errors, and no
absolute machine path. Non-following scans found zero symlinks or reparse
points in both the native source projection and output tree.
