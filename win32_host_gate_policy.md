# Native Windows gate policy

**Effective:** 2026-07-30

The host lab changed its available Windows machines. The former Windows 10
acceptance host is no longer available. Windows Server 2025 Datacenter
Evaluation, x64 build 26100, is now the sole authoritative native gate for
this project.

## Required host for future gates

All future native Windows test packages, acceptance matrices, regression gates,
and release claims must run on the Windows Server 2025 build-26100 host. The
host identity and connection details are recorded in the returned evidence;
credentials must not be stored in source documentation.

The current VM has 16 GiB RAM. Native configure, build, and test commands must
use at most `--parallel 16`; the 32-job policy applies only to Linux and
Windows-cross work on agent01.

Wine, Linux, WSL, and compatibility layers remain useful development or
structural checks, but they do not replace the authoritative native gate.

## Scope and evidence rules

- A passing Server 2025 run is the native acceptance result for future gates.
- The former Windows 10 host must not be listed as an available rerun target.
- Existing Windows 10 build-19044 result bundles remain valid historical
  evidence for the gates they closed at that time; they are not current-host
  evidence and must not be presented as cross-version coverage.
- Do not block FS-4, H-002, or later gates on a second Windows host unless a
  new lab policy explicitly changes this decision.
- When a checklist retains an API compatibility baseline such as Windows 10
  RS4, that is a product/platform minimum, not the current acceptance host.

The policy is referenced by the Windows design documents, unified test
documentation, historical result summaries, and any retained native-host
checklists. Update this file first if the lab's authoritative host changes
again.
