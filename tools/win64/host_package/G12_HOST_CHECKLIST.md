# G12 — Real Windows host golden checklist

Phase 3 is **not complete** until this checklist is executed on a **native Windows 10/11 x64** machine (not WSL, not wine).

## 1. Transfer

From Linux agent (after packaging):

```bash
bash tools/win64/host_package/package_win64_phase3.sh
# artifact: dist/win64_phase3_host/  and  dist/win64_phase3_host.zip
```

Copy the zip or folder to the Windows host. Unpack to a short path if possible, e.g. `C:\art_p3\`.

## 2. Run

```bat
cd C:\art_p3\win64_phase3_host
scripts\run_all_host.cmd
```

## 3. Pass criteria

`logs\RESULT_HOST.txt` must contain:

```text
OVERALL PASS
```

Individual markers (also in `logs\*.log`):

| Script | Required |
|--------|----------|
| run_hello | `Hello from dalvikvm!`, `java.version=1.8.0` |
| run_props | `props.ok=true` |
| run_rtmem | `mem.ok=true` |
| run_core | `CoreProbe.done=ok` |
| run_io | `IoProbe.done=ok` |
| run_oserrno | `OsErrnoProbe.done=ok` |
| run_net | `NetProbe.done=ok` |
| run_dns | `dns.ok=true` |
| run_gc | `gc.ok=true` |
| run_gcforced | `gc.forced.ok=true` |
| run_interrupt | `interrupt.ok=true` |
| run_threadstress | `threadstress.ok=true` |
| run_goldenapp | `golden.ok=true` |
| run_abspath | `AbsPathProbe.done=ok`, `fails=0` |
| run_throw | non-zero exit + `phase3-throw-ok` |

## 4. Return evidence

Copy back into the repo:

```text
tools/verify/win64_phase3/evidence/host/
  RESULT_HOST.txt
  hello.log  (optional other logs)
```

Then update `tools/verify/win64_phase3/RESULT.md` G12 row to **PASS**.

## 5. Non-substitutes

- wine64 package smoke (`smoke_package_wine64.sh`) — agent integrity only
- WSL2 / VM as product runtime — out of mandate
