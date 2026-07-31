# Non-moving heap managed stress probe

`W013NonMovingStressProbe.java` is the managed half of the W-013 non-moving
allocator stress. The existing Windows x86-64 evidence covers low-address
non-moving arrays, allocation churn, forced collections, and address
stability. No other target is currently claimed.

The source is compiled and D8-packaged by the unified target graph. On
2026-08-01, the authoritative Server 2025 Stage-8 run passed both shell-free
managed command gates: 1.34 seconds at `-Xmx128m` and 2.80 seconds at
`-Xmx1024m`. Both sanitized `result.json` files record exit 0, no missing or
forbidden markers, target ID `windows-x86_64-msvc`, and identical boot/app JAR
hashes without host paths.
