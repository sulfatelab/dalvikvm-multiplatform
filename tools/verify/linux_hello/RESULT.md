# L-005 Linux imageless Hello gate

**Status:** PASS
**Date:** 2026-07-17T09:44:51Z
**Host:** agent01

## Command

```
tools/verify/linux_hello/run_imageless_hello.sh
```

## Observed

- `dalvikvm -showversion` prints ART version
- Imageless `-Xint` Hello.main prints `Hello from dalvikvm!` and exits 0
- boot.jar is shared multipath (Unix+WinNT+VMRuntime.isWindowsOs); Linux selects Unix path at runtime

## Artifacts

- log: `tools/verify/linux_hello/last_run.log`
- staged run dir: `/tmp/mdvm_linux_hello_run`
- dalvikvm: `/home/agent/Projects/dalvikvm-multiplatform/build/native/dalvikvm`
- boot.jar source: `/tmp/vm/run/boot.jar`
