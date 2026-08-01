# Unhandled-exception-filter result

The standalone probe covers Windows SEH, process/thread unhandled filters, and
filter chaining. Its current selector is `windows` / `x86_64` / `msvc`.

| Build | Runtime | Last checked |
|---|---|---|
| verified | verified on Windows Server 2025 build 26100 | 2026-08-01 12:35:42 |

The shell-free unified gate passed twice in native `stage:w010`. It accepted
the handled frame-SEH case and the three deliberately nonzero process,
filter-chain, and worker-thread UEF cases, with all required VEH/UEF markers
and no unexpected-return marker. The final stage build was a Ninja no-op.

The same source passed the Linux-hosted Windows cross stage build. Other
architectures and ABIs remain non-applicable.
