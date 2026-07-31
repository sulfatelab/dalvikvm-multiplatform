# Memory-map policy result

The W-013 probe checks ART-owned Windows virtual-memory policy. Its current
selector is `windows` / `x86_64` / `msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | pending unified behavioral gate | 2026-07-31 |

The canonical source passed the unified Windows cross catalog build. Windows
AArch64 and ARM64EC require separate validation before selector expansion.
