# W-025 JIT-5 native host checklist

1. Use the authoritative Windows Server 2025 Datacenter Evaluation x64
   build-26100 host with CET Hardware-enforced Stack Protection disabled for
   the process. The former Windows 10 host is unavailable; see
   `../windows_x64_phase4/HOST_GATE_POLICY.md`.
2. Verify the issued ZIP SHA-256 before extracting it to a fresh local path.
3. Run `powershell.exe -ExecutionPolicy Bypass -File
   .\scripts\RUN_W025_JIT5_HOST.ps1` from the package root.
4. Require 36 PASS records, zero FAIL records, and final `OVERALL PASS`.
5. Preserve the complete package with generated `logs/`, `run/crash/*.dmp`,
   and empty `jit-temp/` as a portable ZIP with forward-slash members.
6. Return the ZIP without editing `BUILD_INFO.txt`, `MANIFEST.json`,
   `SHA256SUMS.txt`, or `W025_JIT5_SOURCE_REPORT.txt`.

The runner covers the 14-record post-removal JIT smoke and 14-workload JIT
matrix, both JIT-disabled controls, default J-2 CriticalNative and 7/7 normal/
FastNative ABI paths, nterp and switch OSR, an eight-cycle lifecycle/reuse
cross-regression, and static/JIT/OSR fatal unwind with exactly three valid
minidumps. The matrix requires `ThrowProbe`'s intentional uncaught
`RuntimeException("phase3-throw-ok")` and process exit `1`; all other nonfatal
children require exit `0`. The added smoke case sets the retired
`ART_WINDOWS_X64_JIT_DUAL=0` key and requires J-2, while the package contract
proves that the opt-out and J-1 fallback strings are absent from source and
`art.dll`. There is no J-1 execution arm.
