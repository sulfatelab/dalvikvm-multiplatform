# W-025 JIT-4 native host checklist

1. Use the authoritative Windows Server 2025 Datacenter Evaluation x64
   build-26100 host with CET Hardware-enforced Stack Protection disabled for
   the process. The former Windows 10 host is unavailable; see
   `../windows_x64_phase4/HOST_GATE_POLICY.md`.
2. Verify the issued ZIP SHA-256 before extracting it to a fresh local path.
3. Run `powershell.exe -ExecutionPolicy Bypass -File
   .\scripts\RUN_W025_JIT4_HOST.ps1` from the package root.
4. Require 34 PASS records, zero FAIL records, and final `OVERALL PASS`.
5. Preserve the complete package with generated `logs/`, `run/crash/*.dmp`,
   and empty `jit-temp/` as a portable ZIP with forward-slash members.
6. Return the ZIP without editing `BUILD_INFO.txt`, `MANIFEST.json`,
   `SHA256SUMS.txt`, or `W025_JIT4_SOURCE_REPORT.txt`.

The runner covers the exact 12-record JIT smoke and 14-workload JIT matrix,
both JIT-disabled controls, default J-2 CriticalNative and 7/7 normal/
FastNative ABI paths, nterp and switch OSR, an eight-cycle lifecycle/reuse
cross-regression, and static/JIT/OSR fatal unwind with exactly three valid
minidumps. The matrix requires `ThrowProbe`'s intentional uncaught
`RuntimeException("phase3-throw-ok")` and process exit `1`; all other nonfatal
children require exit `0`. The runner intentionally contains no J-1 execution
arm.
