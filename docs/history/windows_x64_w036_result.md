# Windows x64 W-036 native result

**Date:** 2026-08-07

**Host:** Windows Server 2025 Datacenter Evaluation, x64, build 26100

**Status:** **PASS — representative ordinary boot-OAT dispatch is proven;
numbered step 10 remains partial**

## Scope and conclusion

W-036 proves that an ordinary Java call can execute at the exact current
registered boot-OAT entry PC. It does not infer execution from structural OAT
lookup and does not directly call the address returned by
`ArtMethod::GetOatMethodQuickCode()`.

The gate selected `Integer.parseInt(String)`, required its current
`ArtMethod` quick entrypoint to equal the underlying OAT quick entrypoint and
the beginning of an exact registered `RUNTIME_FUNCTION`, and armed a one-shot
x64 hardware execute breakpoint on a dedicated worker. The worker invoked the
method through ordinary Java bytecode with JIT disabled. A first-priority VEH
observed the expected RX PC exactly once, restored the worker's prior debug
register state, and resumed normal execution.

The authoritative markers were:

```text
W036_BOOT_OAT_DISPATCH_PASS target=int java.lang.Integer.parseInt(java.lang.String) current_entry=oat rx_pc=hardware_breakpoint hits=1 wrong_single_steps=0 jit=disabled
W036BootOatDispatchProbe PASS dispatch=ordinary rx_pc=observed jit=disabled
```

This closes the representative ordinary-dispatch condition in numbered step
10. The step remains partial because relocation, fault, GC/root, exception,
and fatal stack-walk coverage still remains.

## Runtime correction

The Windows x64 post-start nterp visitor is an imageless-startup repair. It
updates eligible managed methods left on the switch-interpreter bridge while
nterp was unavailable early in `Runtime::Start()`. The visitor previously
called `ReinitializeMethodsCode()` for every nterp-eligible method, which also
replaced already-published boot-AOT entrypoints with nterp.

W-036 scopes the visitor to its stated purpose. It now checks the current
entrypoint and skips every method not using the switch-interpreter bridge.
Compiled boot-image entrypoints remain published; methods genuinely left on
the imageless switch bridge retain the existing nterp repair.

## Source identity

The native overlay was deployed at:

```text
source  C:\mdvm-w028-8d3037c\src
output  C:\mdvm-w028-8d3037c\out
```

The deployed root baseline was
`7013398e219b5e9b65b01f8167cbf6830a41d66d`. The accepted runtime correction
is nested ART commit `03d55ca0174dbf39b54444ce5fdf4a55e5dce331`;
the containing root commit owns the probe, test catalog, accepted record, and
submodule update.

Selected local and native-overlay files matched byte-for-byte:

```text
vendor/art/runtime/runtime.cc
8d2c8aab6ced647c347bca1ef0c88d87ac49e83e3f9e8849cfabbc0a879bf954

tests/CMakeLists.txt
ef887a80b41b19fad00447f2aed254eb87f4a7afd4f1183af478064fe370cbd1

tests/cases/aot-dispatch/probe.cc
e5633a6af267f670443a2fcdec35d03770f882fd938004fb85872f7b861c3b44

tests/cases/aot-dispatch/W036BootOatDispatchProbe.java
0362fd7797159085c982343e19d16f7fbc0cdf690504110215dd88ddf6c167d8
```

## Native command and result

After deploying and reconfiguring the native workspace, the authoritative
gate used the repository frontend:

```text
python.exe tools\build_art.py test \
  --target-id windows-x86_64-msvc \
  --output-root C:\mdvm-w028-8d3037c\out \
  --stage w036 \
  --parallel 16
```

The existing Ninja dependency log emitted its known `premature end of file;
recovering` warning. Recovery, the affected rebuild, a fresh boot-cache
generation, and the native test all completed successfully:

```text
art.w036.managed_w036_aot_dispatch  PASS  1.26 s
1/1 PASS
```

The result manifest recorded exit 0, all required markers present, no
forbidden marker, and all seven intentional launcher identity mismatches
rejected. `dalvikvm` reported `main end exception=0`.

The affected native boot-OAT regression stages then passed together against a
fresh cache generation:

```text
python.exe tools\build_art.py test \
  --target-id windows-x86_64-msvc \
  --output-root C:\mdvm-w028-8d3037c\out \
  --stage w030 --stage w031 --stage w032 --stage w036 \
  --parallel 16

W-030  2/2 PASS
W-031  1/1 PASS
W-032  3/3 PASS
W-036  1/1 PASS
7/7 PASS
```

The cross-host Windows build also compiled the changed runtime, the managed
probe, and `libw036aotdispatchprobe.dll`. The native probe DLL was 33,280
bytes with SHA-256
`95a850bfd39ee8509901408dbb8290b911ef9b19322b0dd7bf8a299ff32d7a96`.

Fresh agent01 regression evidence passed:

```text
Python bp2cmake/tool suite                         225/225 PASS
linux-x86_64-gnu configure and target audit       PASS
  2,089 compile commands; 2,172 Ninja commands; 32 product links
full linux-x86_64-gnu build and boot generation   PASS
Linux catalog                                     15/15 PASS
```

## Accepted cache set

The accepted path-sensitive cache set was:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `boot.art` | 2,940,464 | `d86014e2ff75383b682dd0c1f1169289c415ba2d30ae96bcb0e92a19d5d94fbe` |
| `boot.oat` | 20,169,448 | `fb77ee81ddd419251c02e4ba6c1847009bae4c3e34aa4cfd0bf5b99fd7a1d663` |
| `boot.vdex` | 8,309,376 | `acec8006a073b67bd1740804a7bd65a0a1ffa5380815cb194eff9443845fc12d` |

These hashes bind this one passing generation. ART/OAT files are
path-sensitive caches; cross-generation byte identity is not an acceptance
condition.

## Why the observation is direct

- Candidate selection reads both entrypoints but accepts only exact equality;
  it does not invoke either pointer.
- `RtlLookupFunctionEntry()` must return an exact function-begin record whose
  image base contains a valid OAT header.
- The breakpoint is installed only in the worker's debug-register state. The
  worker is released after the selected index and arm state are published.
- The Java switch contains the ordinary statically typed method call. No
  reflection invocation or native quick-call bridge performs the dispatch.
- The exception handler accepts only `EXCEPTION_SINGLE_STEP` on the registered
  worker at the exact expected `RIP`, restores the prior slot-zero state, and
  counts exactly one hit.
- Verification rechecks that the method still publishes the same registered
  OAT entrypoint after the call.

## Disposition

- The representative ordinary-dispatch requirement of step 10 is accepted.
- Step 10 remains `PARTIAL` for relocation, managed faults, GC/roots,
  exceptions, and fatal stack walking.
- Step 6 remains `PARTIAL`; W-036 does not replace unwind corruption/fallback,
  exception/fatal walking, or actual XMM-bearing boot-AOT frame coverage.
- Step 11 remains `PARTIAL`; W-036 does not make an OAT-2 or explicit-CFG
  allocation decision.
- Product selection, successful imageless fallback, application OAT,
  successful unloading, outgoing quick-code CFG instrumentation, and security
  hardening remain outside this gate.
