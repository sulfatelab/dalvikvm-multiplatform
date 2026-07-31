# W-013 source-policy result

The shell-free host reviewer pins the Windows `MemMap` address-requirements
implementation, page-state ownership boundary, heap/JIT mspace lock
assertions, exclusive raw-mspace creation ownership, provider attachment
tokens, anywhere-mapped runtime metadata and card table, unconditional write
barriers, and the exact eight-file required-low caller inventory.

| Target selector | Host review | Last checked |
|---|---|---|
| `windows` / `x86_64` / `msvc` | verified | 2026-08-01 |

```text
W013_SOURCE_POLICY_PASS low_address_files=8 page_transition_files=4 mspace_lock_assertions=2 mspace_attachment_tokens=6 raw_mspace_creation_files=1 metadata=anywhere card_mark=unconditional nonmoving_barrier=unconditional
```

The reviewer reads only repository source, invokes no shell or external search
tool, and emits repository-relative diagnostics. The historical exhaustive
low-VA runtime closure remains documented separately; this review proves that
the product implementation has one constrained `VirtualAlloc2` path and no
manual scan or unrestricted fallback.

After absorbing the last dlmalloc source checks from the historical Bash
runner, the authoritative Server 2025 Stage-8 build remained a Ninja no-op and
passed all seven registered W-013 tests in 25.16 seconds on 2026-08-01. The
reviewer's cold-tree scan completed in 22.24 seconds; an immediate standalone
rerun completed in 2.01 seconds with the marker above.
