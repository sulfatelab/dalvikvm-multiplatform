# L-005 Linux imageless Hello gate

**Status:** PASS
**Date:** 2026-07-24 07:10:46 UTC
**Host:** agent01

## Command

```
tools/verify/linux_hello/run_imageless_hello.sh
```

## Observed

- `dalvikvm -showversion` prints ART version
- Imageless `-Xint` Hello.main prints `Hello from dalvikvm!` and exits 0
- boot.jar is the shared Linux+Win64 multipath artifact; ELF selected UnixFileSystem

## Artifacts

- log: `tools/verify/linux_hello/last_run.log`
- staged run dir: `/tmp/mdvm_linux_hello_run`
- dalvikvm: `/home/agent/Projects/dalvikvm-multiplatform/build/native/dalvikvm`
- boot.jar source: `/home/agent/Projects/dalvikvm-multiplatform/build/win64_phase1/run/boot.jar`
