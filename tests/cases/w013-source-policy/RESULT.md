# W-013 source-policy result

The shell-free host reviewer pins the Windows `MemMap` address-requirements
implementation, page-state ownership boundary, heap/JIT mspace lock
assertions, anywhere-mapped runtime metadata and card table, unconditional
write barriers, and the exact eight-file required-low caller inventory.

| Target selector | Host review | Last checked |
|---|---|---|
| `windows` / `x86_64` / `msvc` | verified | 2026-08-01 |

```text
W013_SOURCE_POLICY_PASS low_address_files=8 page_transition_files=4 mspace_lock_assertions=2 metadata=anywhere card_mark=unconditional nonmoving_barrier=unconditional
```

The reviewer reads only repository source, invokes no shell or external search
tool, and emits repository-relative diagnostics. The historical exhaustive
low-VA runtime closure remains documented separately; this review proves that
the product implementation has one constrained `VirtualAlloc2` path and no
manual scan or unrestricted fallback.

The authoritative Server 2025 Stage-8 build was a Ninja no-op and passed all
seven registered W-013 tests in 6.89 seconds. This host-review gate completed
in 3.69 seconds with the marker above.
