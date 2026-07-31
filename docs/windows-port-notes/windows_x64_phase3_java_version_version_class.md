# Windows x64 Phase 3 — java.version stuck at "0"

Status: applied and superseded by the shared boot-jar source-selection design.
The current build selects the ojluni/multipath
`AndroidHardcodedSystemProperties` with `JAVA_VERSION = "1.8.0"` before compiling
`sun.misc.Version`; the old Windows-only overlay step is only a legacy fallback.

**Symptom:** `System.getProperty("java.version")` remained `"0"` even after overlaying
`AndroidHardcodedSystemProperties.JAVA_VERSION = "1.8.0"` into boot.jar.

**Cause:** `sun.misc.Version.initSystemProperties()` runs after hardcoded STATIC_PROPERTIES
and calls `System.setUnchangeableSystemProperty("java.version", java_version)`.
`java_version` is a **compile-time constant** folded from
`AndroidHardcodedSystemProperties.JAVA_VERSION` when `Version.java` was compiled
against the vendor default (`"0"`).

**Original fix:** Recompile
`vendor/libcore/ojluni/src/main/java/sun/misc/Version.java` together with the
Windows `AndroidHardcodedSystemProperties.java` overlay. The legacy
`tools/bootjar/build_windows_x64.sh` still demonstrates that fallback, while
`tools/bootjar/build.sh` implements the current shared-source policy.

**Verify:** Hello / PropsProbe print `java.version=1.8.0`.
