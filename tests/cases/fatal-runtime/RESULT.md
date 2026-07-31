# Fatal runtime managed probes

`CrashAbortProbe.java` and `CrashNativeProbe.java` are the managed entrypoints
for the Windows fatal-abort and native-crash/unwind checks. They were retained
from the Phase-4 bring-up suite and are currently applicable only to
`windows-x86_64-msvc`.

The historical native-host result remains recorded in the W-010 evidence while
its package runner is migrated. The unified graph now compiles and D8-packages
both sources under the target build tree; that build result is not yet a
replacement for the fatal-exit, unwind, and dump-review runtime gates.
