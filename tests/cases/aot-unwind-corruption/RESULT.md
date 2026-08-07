# Windows boot-OAT unwind corruption and fallback result

The Windows x86-64 W-039 case validates semantic rejection of corrupted
`.oat_unwind.windows` transports through both real `ElfOatFile` open modes,
canonical function-table registration and deletion, and diagnosed
whole-transaction imageless fallback.

| Build | Runtime | Last checked |
|---|---|---|
| Windows x86-64/MSVC cross-build PASS | Windows Server 2025 build 26100: W-039 1/1 PASS; affected boot-OAT regression 10/10 PASS | 2026-08-08 |

The gate owns 23 independently checksummed mutations across the serialized
header, function entries, `UNWIND_INFO` operations, and odd-slot padding. All
23 reject through both real open modes with unwind-specific diagnostics; the
canonical table registers and unregisters cleanly; and all 23 staged
corruptions fall back imageless with zero boot image spaces. The authoritative
record is `docs/evidence/windows_x64_w039_result.md`.
