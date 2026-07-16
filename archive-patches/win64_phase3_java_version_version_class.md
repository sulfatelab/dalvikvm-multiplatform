# Win64 Phase 3 — java.version stuck at "0"

**Symptom:** `System.getProperty("java.version")` remained `"0"` even after overlaying
`AndroidHardcodedSystemProperties.JAVA_VERSION = "1.8.0"` into boot.jar.

**Cause:** `sun.misc.Version.initSystemProperties()` runs after hardcoded STATIC_PROPERTIES
and calls `System.setUnchangeableSystemProperty("java.version", java_version)`.
`java_version` is a **compile-time constant** folded from
`AndroidHardcodedSystemProperties.JAVA_VERSION` when `Version.java` was compiled
against the vendor default (`"0"`).

**Fix:** Recompile `vendor/libcore/ojluni/src/main/java/sun/misc/Version.java` together
with the Windows `AndroidHardcodedSystemProperties.java` overlay in
`tools/bootjar/build_win64.sh`, copy `sun/misc/Version.class` into the boot class tree,
re-dex boot.jar.

**Verify:** Hello / PropsProbe print `java.version=1.8.0`.
