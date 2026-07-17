# L-003 wine matrix

**Status:** PASS
**Date:** 2026-07-17
**Command:** `tools/verify/win64_phase3/run_l003_wine.sh`

## Results

| Probe | Status |
|-------|--------|
| ExecProbe | PASS (`ExecProbe.done=ok`) |
| LocaleProbe | PASS (`LocaleProbe.done=ok`; Collator soft-skip without ICU data) |
| ZipProbe | PASS (`ZipProbe.done=ok`; multi-entry DEFLATED + ZipFile) |
| UdpProbe | PASS (`UdpProbe.done=ok`) |
| Ipv6Probe | PASS (`Ipv6Probe.done=ok`; Os.socket AF_INET6 bind on `::`) |

## Notes

- ZipFile CEN uses heap read + DirectByteBuffer mirror on Windows (mmap CEN path invalid under wine).
- IPv6 gate avoids reverse-DNS (`getHostAddress` hang under wine).
- TCP IPv4-mapped dual-stack remains host residual / wine partial.
