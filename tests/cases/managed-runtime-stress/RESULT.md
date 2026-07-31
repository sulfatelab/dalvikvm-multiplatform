# Managed runtime stress probes

This case owns the retained handle-leak, performance-smoke, and heavy-thread
managed sources. Their accepted evidence came from the Windows x86-64 Phase-4
runtime package, so their current selector is exactly the implemented Windows
x86-64 MSVC profile.

The unified build produces their DEX JARs with configured JDK 21 and the pinned
in-tree D8. Runtime execution and expected-marker review remain pending until
the old package runner is replaced by the shared Python runner.
