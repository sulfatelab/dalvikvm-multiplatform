# ART UEFI switch-interpreter, offline AOT, and PosixShim feasibility analysis

Status: feasibility assessment

Date: 2026-08-07

## Executive conclusion

Cross-compiling the current ART product unchanged into a UEFI application is
not feasible. UEFI can execute physical x86-64, AArch64, and, in the platform
specification, RISC-V64 instructions, but it is a firmware execution
environment rather than an operating system. It does not provide ART's current
process, pthread, signal/fault, virtual-memory, dynamic-loader, DSO, and JIT
contracts.

A deliberately restricted ART-derived UEFI runtime is technically feasible as
a research project. Its credible initial form is:

- one statically linked PE32+ UEFI application, with no DLL imports;
- execution only while UEFI Boot Services remain available;
- an imageless DEX boot through the portable C++ switch interpreter;
- a project-owned PosixShim over selected UEFI services and protocols;
- packaged boot DEX/JAR data and a generated static JNI registry;
- explicit Java null, bounds, divide, and stack-depth checks instead of
  recoverable hardware faults;
- a single-managed-thread bring-up fork; and
- later, selective physical-ISA AOT generated offline and included in the
  signed UEFI image at link time.

That runtime would not be current ART. It would remove or replace daemon-thread
startup, pthread scheduling, signal-based implicit checks, dynamic JNI loading,
native DSOs, runtime JIT, current ELF OAT loading, and substantial libcore OS
behavior. A one-thread proof is useful staging, but it cannot satisfy the
canonical ART target contract: current ART starts Java daemon threads and
internal worker pools, and Java threading is not an optional optimization.

The repository therefore correctly classifies all three canonical profiles as
`impossible_under_current_art_contract`:

- `uefi-x86_64-posixshim`;
- `uefi-aarch64-posixshim`; and
- `uefi-riscv64-posixshim`.

RISC-V64 has an independent toolchain blocker. The profile requires PE32+,
while the tested Clang 21.1.8 Windows-style RISC-V64 target emits ELF rather
than COFF. An accepted target triple or an `.obj` filename is not a UEFI image
path.

UEFI is nevertheless more favorable than browser WebAssembly for compiled
methods. A UEFI application has real physical-ISA function addresses,
byte-addressable executable code, and ART-supported instruction families.
`ArtMethod` quick entrypoints, adjacent `OatQuickMethodHeader` metadata, and
quick-frame concepts can remain meaningful if compiled code is placed in the
firmware-loaded image. This removes the Wasm function-table/code-address
mismatch described in
[`art_wasm64_feasibility.md`](art_wasm64_feasibility.md), but it does not supply
the missing operating-system contracts.

The resulting judgment is:

| Goal | Judgment |
|---|---|
| Cross-compile and run the current ART product unchanged | No-go |
| Preserve the current shared-library topology inside UEFI | No-go; UEFI loads independent images and exposes protocols, not process DSOs |
| Boot a reduced, single-image runtime through the C++ switch interpreter | Conditional go for a research fork |
| Use existing x86-64/AArch64/RISC-V64 ART ISA machinery | Partly reusable after firmware ABI, TLS, stack, fault, and runtime-entry adaptation |
| Run `dex2oat` inside firmware | No-go for the initial design and unnecessary for offline packaging |
| Include offline-compiled quick code in the signed `.efi` image | Conditional go; substantially easier than Wasm AOT, but requires a new link/artifact path |
| Load an ELF OAT file and make copied code executable at runtime | Not a portable UEFI baseline |
| Keep current ART JIT mapping and W^X behavior | No-go |
| Implement a curated PosixShim over Boot Services and protocols | Conditional go |
| Treat UEFI events or timer callbacks as pthreads | No-go |
| Map one Java/pthread thread directly to one AP | No-go; APs are a finite, busy-dispatched processor set rather than logical thread objects |
| Build an M:N PosixShim scheduler over a usable processor substrate | Mandatory for ART semantics, research-scale, and not provided by MP Services alone |
| Continue the same runtime after `ExitBootServices()` | No-go without becoming a freestanding kernel or operating system |
| Use a UEFI Shell as the POSIX layer | No-go; the shell is optional and is not POSIX |
| Admit x86-64 first under QEMU/OVMF and real firmware | Reasonable research order, not a support claim |
| Admit UEFI RISC-V64 with the current Clang path | No-go because direct COFF emission is absent |

## Target identity and PosixShim boundary

The canonical grammar is
`<target-platform>-<target-arch>-<target-abi>`. `uefi` names the firmware
execution environment, `x86_64`, `aarch64`, or `riscv64` names the physical
target architecture, and `posixshim` names the project-owned libc,
compatibility, and firmware-service ABI. Firmware vendor, machine model,
Secure Boot state, UEFI Shell presence, OVMF, and QEMU are capability or test
facts, not target-identity axes.

Every UEFI ART target is always built and shipped with PosixShim. There is no
valid UEFI ART profile using `gnu`, `msvc`, an EDK II library ABI, a UEFI Shell
ABI, or an unshimmed contract. The current registry's Windows-style Clang
triples are provisional COFF-emission facts; they do not change
`target_abi=posixshim` into the Windows API or MSVC runtime contract.

ART-facing source selection uses `ART_TARGET_UEFI`. It must not branch on
OVMF, AMI, Insyde, EDK II, a board name, or whether execution is virtualized.
Those implementations sit below a versioned firmware backend. The complete
identity and capability decision remains owned by the target profile described
in [`unified_art_build.md`](../../unified_art_build.md).

PosixShim owns the ART-facing libc and system contract. It supplies the
implemented, virtualized, and unsupported behavior for memory allocation,
files and descriptors, clocks, entropy, polling, synchronization, system
identity, and the admitted libcore surface. Its UEFI backend reaches Boot
Services, Runtime Services, and explicitly required protocols through narrow
adapters. ART and libcore do not call firmware tables directly throughout the
product.

The PosixShim ABI version is immutable profile metadata and participates in
manifests, fingerprints, and AOT compatibility checks. It is not encoded in
the canonical target ID.

## UEFI execution boundary

### Boot Services are the proposed host environment

The only practical first runtime stays inside a UEFI application and never
calls `ExitBootServices()`. Before that transition, the application may use
page and pool allocation, events and timers, image services, protocol
discovery, watchdog control, console devices, filesystem protocols, and any
optional networking or entropy protocols supplied by the firmware.

This is still a narrow and unusual application environment:

- firmware protocols are capability-discovered and may be absent;
- implementations differ materially in limits, correctness, and performance;
- service calls have task-priority-level rules rather than process/thread
  scheduling semantics;
- the application normally runs on the bootstrap processor;
- a long-running application must manage the firmware watchdog explicitly;
- the UEFI Shell is not guaranteed to have launched the image; and
- a protocol available under OVMF is not automatically a hardware baseline.

`ExitBootServices()` is a hard semantic boundary. After it succeeds, all Boot
Services and boot-service protocols become unavailable. Only the limited UEFI
Runtime Services contract and memory preserved for it remain. Filesystems,
network stacks, events, image loading, ordinary allocation, console protocols,
and multiprocessor boot services cannot be treated as continuing services.

An ART system intended to survive that transition would need to own physical
memory, page tables, interrupts, timers, processor startup, scheduling, TLS,
device drivers, storage, networking, and fault dispatch. That is an operating
system kernel. Its correct target identity would describe that operating
system's ABI, not `uefi-*-posixshim`.

### Runtime Services are not an operating system

UEFI Runtime Services provide facilities such as variables, time, capsule
updates, reset, and virtual-address-map transition. They do not provide a heap,
threads, files, sockets, a dynamic loader, signals, or general scheduling.
Remaining in firmware runtime mode after `ExitBootServices()` therefore does
not rescue the ART contract.

### Events and task priority levels are not threads

UEFI events can be signaled, waited upon, and associated with notification
callbacks. Timer events can wake a wait or invoke a callback. Notifications run
under firmware task-priority-level rules and are cooperative callbacks, not
independent pthreads with managed stacks, per-thread TLS, blocking syscalls,
preemption, signal masks, and Java thread lifecycle.

The
[PI MP Services Protocol](https://github.com/tianocore/edk2/blob/master/MdePkg/Include/Protocol/MpService.h)
exposes a finite set of logical processors. PI requires the protocol on a
system with more than one logical processor, but a single-processor system has
no AP capacity. `StartupThisAP` and `StartupAllAPs` dispatch one
caller-provided procedure to an idle AP; a busy target produces
`EFI_NOT_READY`. They do not create another schedulable context on that AP, and
the protocol does not provide thread stacks, TLS, preemption, blocking,
joining, or a run queue.

ART does not need a literally infinite thread count; every implementation is
resource-bounded. It does need dynamically many Java/pthread logical
threads whose limit is not the number of hardware processors. A direct
one-thread-per-AP mapping would reject normal workloads once all APs are busy.
PosixShim therefore needs an M:N scheduler that multiplexes owned logical
thread contexts over a finite set of execution contexts and supplies context
switching, stacks, TLS, blocking/wakeup, timers, interruption, and ART
safepoints.

MP Services is also a weaker substrate than a normal fixed worker pool. The PI
contract says nonblocking `StartupThisAP`/`StartupAllAPs` requests are
unsupported after `ReadyToBoot`, and UEFI applications execute after that
event. AP procedures generally may not call UEFI services or protocols unless
the relevant contract says otherwise. A scheduler would therefore need a
separately proven way to keep workers running and marshal firmware operations
to the BSP; MP Services alone may not provide a portable way to do so.

## Why the current tree cannot simply be cross-compiled

| Area | Current finding |
|---|---|
| Build admission | [`target.py`](../../tools/bp2cmake/bp2cmake/target.py) registers all three UEFI identities but rejects them before graph generation with `impossible_under_current_art_contract`. |
| Product entry point | [`native/CMakeLists.txt`](../../native/CMakeLists.txt) implements admitted Linux and Windows platform mappings, not a freestanding UEFI product. |
| Image format | UEFI applications are PE32+ images with a UEFI subsystem and entrypoint. The current product emits ELF executables/DSOs or Windows PE executables/DLLs with operating-system imports. |
| C and C++ runtime | ART, libc++, ICU, OpenJDK, BoringSSL, and support libraries expect a hosted libc, allocator, TLS, time, files, synchronization, and other runtime support. Firmware supplies none as a C ABI. |
| DSO topology | The unified product deliberately requires native shared-library topology, including a shared `art-compiler`. UEFI has `LoadImage`/`StartImage` for independent firmware images and protocols, not a process DLL namespace with imports, `dlopen`, and `dlsym`. |
| ART ISA | [`instruction_set.h`](../../vendor/art/libartbase/arch/instruction_set.h) already recognizes x86-64, ARM64, and RISC-V64, so `kRuntimeISA` can be real rather than `kNone`. This is necessary but far from sufficient. |
| Interpreter entry | The portable C++ switch interpreter is promising, but its surrounding quick/JNI bridges, TLS, stack handling, and selected assembly are built for hosted target ABIs. |
| Runtime startup | [`runtime.cc`](../../vendor/art/runtime/runtime.cc) starts daemon threads and runtime services; [`thread.cc`](../../vendor/art/runtime/thread.cc) and [`thread_pool.cc`](../../vendor/art/runtime/thread_pool.cc) create pthreads. |
| Memory | ART `MemMap` assumes reserve/map/unmap/protect operations, file mappings, exact placement, and low-4-GiB allocation. UEFI exposes page/pool allocation but not process virtual-memory mappings. |
| JIT | [`jit_memory_region.cc`](../../vendor/art/runtime/jit/jit_memory_region.cc) assumes executable mappings, protected views, file/pagefile backing, and W^X transitions. UEFI has no portable application contract matching those operations. |
| Faults | [`fault_handler.cc`](../../vendor/art/runtime/fault_handler.cc) installs recoverable signal handlers. Firmware CPU exceptions do not arrive as portable `sigaction`/`ucontext` records that ART may rewrite and resume. |
| OAT | Current OAT loading is ELF-oriented and uses mapping/protection or dynamic-loading behavior; Windows support is a separate experimental private-copy path. UEFI does not provide either an ELF loader or Windows runtime unwind APIs. |
| JNI | Runtime startup loads libcore and ICU JNI DSOs and application code may use `System.loadLibrary`. A UEFI runtime needs a packaging-time static registry. |
| Files and sockets | UEFI protocols are handle/token/event interfaces. They do not supply POSIX descriptors, paths, sockets, DNS, polling, process identity, or `errno` behavior. |
| Stack walking | Managed quick metadata can remain addressable, but native unwind and fatal-context capture need firmware-specific implementations. There is no `RtlVirtualUnwind`, POSIX unwinder contract, or resumable signal context. |
| Heap references | Managed references remain compressed 32-bit values. The Java heap must fit entirely below 4 GiB even though all UEFI profiles are 64-bit. |
| RISC-V64 | ART has a RISC-V64 backend, but the current Clang path does not emit the required RISC-V64 COFF/PE image. |

The block is architectural rather than a missing CMake branch. Enabling the
profile, turning every DSO into a static archive, and providing empty POSIX
stubs could produce compilation progress while violating the product contract.
The repository is correct to fail before graph generation.

## What physical-ISA UEFI preserves

The UEFI case should not be modeled as WebAssembly with a different host API.
The execution and address models are fundamentally different:

| Property | Browser Wasm | UEFI physical ISA |
|---|---|---|
| Method code | Opaque Wasm functions in a function/table index space | PE-loaded physical-ISA bytes with ordinary code addresses |
| C function pointer | Toolchain table slot, not a linear-memory code address | Ordinary callable pointer in the firmware application's address space |
| Return PC | Engine-private | Physical return address, subject to the target ABI |
| Adjacent method header | Cannot precede engine code | Can be laid out next to link-time AOT code |
| Existing ART ISA backend | New Wasm backend required | x86-64, ARM64, and RISC-V64 backends exist |
| Runtime-generated code | Guest memory is never executable | Technically possible on some machines, but no portable UEFI W^X/security contract |
| Main missing layer | New code/method model plus browser OS emulation | Firmware OS/runtime contract plus ABI adaptation |

This makes a restricted UEFI AOT runtime more plausible than ART AOT in Wasm.
It does not make current OAT files firmware images. The existing OAT loader,
ELF container, mapping operations, runtime trampolines, native unwind, and DSO
assumptions still require replacement or adaptation.

## Proposed restricted execution architecture

The recommended research architecture packages all executable code before
firmware launch:

```text
                         offline build and packaging host
                +-----------------------------------------------+
DEX/JAR --------+--> retained DEX, metadata, and packaged assets |
                |                                               |
                +--> ART HGraph/ISA backend --> quick code -----+--+
                |                                                  |
C/C++ runtime --+--> Clang/LLD, static libc/PosixShim/JNI ---------+
                                                                   |
                                                                   v
                                                        art-runtime.efi
                                                        one signed PE32+ image

firmware execution:

art-runtime.efi
  -> validate image-local manifest and packaged DEX hashes
  -> reserve the low-4-GiB managed heap while Boot Services exist
  -> initialize PosixShim and required protocols
  -> create the reduced ART runtime
  -> run switch-interpreted methods
  -> dispatch selected methods to image-resident AOT entrypoints
```

The initial `.efi` should contain:

- the reduced ART runtime and C++ switch interpreter;
- statically linked required libcore JNI, ICU/OpenJDK, allocator, and libc
  components;
- the complete UEFI PosixShim backend;
- a packaging-time JNI and runtime-helper registry;
- boot DEX/JAR data in a read-only image section or a verified sidecar;
- a manifest binding target ID, PosixShim ABI, DEX identities, compiler
  revision, required protocols, memory limits, and optional AOT metadata; and
- eventually, link-time AOT code and its adjacent stack-map/method metadata.

The deployed image does not contain `dex2oat`, `art-compiler`, a native DSO
loader, or a JIT. Offline compiler tools are build-host programs and are not
part of the firmware artifact.

### Why one image is the initial contract

UEFI `LoadImage` and `StartImage` load another independent firmware image.
They do not establish ELF/PE DLL imports, one C++ global namespace, shared TLS,
or `dlsym` lookup. UEFI protocols are appropriate for coarse firmware-service
interfaces, not ART's private C++ DSO boundaries or per-method JNI calls.

The initial research runtime must therefore link all code statically into one
image. This intentionally violates the admitted native product's DSO topology
invariant and is one reason the result is a fork rather than an enabled UEFI
profile. Splitting the runtime into several `.efi` images would add protocol
marshalling without recreating process-local DSOs.

### Execution-mode progression

| Mode | Role | Feasibility |
|---|---|---|
| Switch interpreter | Decisive first boot and fallback for dynamic or unsupported DEX | Feasible after runtime/PosixShim reduction |
| Image-resident offline AOT | Selected closed-world methods compiled for the exact physical ISA and linked into `.efi` | Preferred compiled-method design |
| Runtime-loaded external OAT | Read code from a file, allocate executable pages, relocate, protect, flush caches, and register unwind | Possible only with a new capability contract; exclude initially |
| JIT/OSR | Generate and publish code during firmware execution | Exclude; current JIT contract is unavailable |
| nterp/mterp | Architecture assembly interpreter paths | Defer until firmware ABI, stack, TLS, and unwind behavior are proven |

The switch interpreter must remain after AOT exists for methods omitted by
offline compilation, newly loaded DEX, debugger-forced interpretation, and
safe fallback after metadata mismatch.

## Offline AOT and artifact model

### Reuse the physical ART compiler backend selectively

The ART compiler already lowers DEX/HGraph to x86-64, ARM64, and RISC-V64 quick
code. Unlike a Wasm port, UEFI does not need a new instruction backend or a
function-table dispatch ABI. It does need a new output and link contract.

The safest AOT design makes every compiled byte part of the firmware-loaded
PE image. A packaging tool can extract or emit method code, headers, stack
maps, literals, trampolines, and relocation records into linkable target
sections. LLD then assigns final addresses and emits PE base relocations as
needed. The runtime manifest maps each DEX method to an image-relative entry
and metadata record.

This preserves the useful physical quick-code properties:

- an `ArtMethod` can contain an actual callable entrypoint;
- an `OatQuickMethodHeader`-shaped record can be adjacent to code;
- compiled frames can publish real return PCs;
- PC-to-method and stack-map lookup can use bounded image ranges; and
- direct calls and runtime trampolines can remain physical-ISA operations.

It does not imply that the current OAT ELF file is embedded unchanged. The
offline linker must define how relocations, runtime helper calls, method
headers, literals, read-only data, stack maps, and image rebasing interact.
Any code that assumes an ELF load bias, symbol table, `mmap`, `mprotect`, or
`dlopen` must be removed from the firmware path.

### Recommended artifacts

| Artifact | Purpose |
|---|---|
| `art-runtime.efi` | Only executable product artifact; contains runtime, PosixShim, JNI registry, and optional AOT code |
| Original DEX/JAR | Authoritative bytecode, class metadata, reflection/debug input, and interpreter fallback |
| Firmware manifest | Target ID, ABI versions, required protocols, heap bounds, image/AOT ranges, DEX hashes, compiler identity, and policy |
| Optional data sidecar | Read-only packaged assets too large for the PE image; authenticated by the manifest before use |

External executable AOT sidecars are deliberately absent. Keeping AOT code in
the signed PE image aligns execution with the firmware loader and Secure Boot
trust decision. A later external-code experiment would need an explicit
authenticated loader, executable-memory policy, instruction-cache maintenance,
relocation model, unwind registration, and negative security tests.

### Secure Boot implications

Secure Boot authenticates the firmware image before execution; it does not
automatically authenticate arbitrary method bytes read later from a file and
made executable. Runtime code generation or external executable OAT would also
interact poorly with firmware memory-protection policies intended to keep data
non-executable.

The preferred model signs one immutable `.efi` image after all native and AOT
code is linked. Sidecar DEX/data may remain non-executable, but its digest and
logical identity must be covered by the image manifest and verified before ART
parses it. Development under OVMF with Secure Boot disabled is useful bring-up
evidence, not production security evidence.

## Architecture and ABI considerations

### Native ISA does not mean native platform ABI

`kRuntimeISA` and `kRuntimeQuickCodeISA` can resolve to ART-supported values on
all three UEFI architectures. That allows reuse of instruction decoding,
quick-code generation, stack maps, and substantial assembly. The surrounding
C/C++ and firmware-call ABI still has to be exact.

| Target | Useful existing base | Required independent work |
|---|---|---|
| x86-64 | ART x86-64 backend; current repository PE/x86-64 experience; mature Clang COFF and OVMF path | UEFI x64 call ABI, no red zone, firmware entry/thunks, freestanding TLS/libc, static runtime, firmware stack/fault behavior |
| AArch64 | ART ARM64 backend and admitted Linux AArch64 graph; Clang emits AArch64 COFF | UEFI/AAPCS boundary review, PE relocations, cache maintenance for any dynamic code, native unwind, firmware protocol validation |
| RISC-V64 | ART RISC-V64 backend and UEFI-defined machine architecture | Direct RISC-V64 COFF/PE emission, linker/image validation, firmware availability, ABI and cache/unwind work |

The current UEFI profiles use `x86_64-pc-windows-msvc` and
`aarch64-pc-windows-msvc` to obtain COFF, and use `Generic` as CMake's system
name. Those are registry facts, not a finished toolchain design. The UEFI
platform layer must select firmware headers, the UEFI subsystem, entrypoint,
static runtimes, and PosixShim sources without inheriting Win32 libraries or
Windows source selection.

At every call from C/C++ into firmware, the exact `EFIAPI` calling convention
must be visible in the function type. On x86-64 this is particularly important
because firmware follows the UEFI x64 convention rather than a Unix System V
ABI. A successful COFF compile does not prove that indirect firmware calls,
variadic functions, structure returns, stack alignment, or unwind metadata are
correct.

### Switch first, assembly later

The portable switch interpreter minimizes dependence on quick-entry assembly,
implicit-fault handling, and compiled-frame unwind. Its outer entry must still
be a UEFI-safe C++ path with known stack alignment and explicit `Thread*`
state.

nterp, mterp, quick JNI, generic JNI, and resolution trampolines may eventually
reuse architecture sources only after each source is audited for:

- hosted-OS TLS or segment-register assumptions;
- signal and implicit-null-check behavior;
- stack probing and overflow guards;
- platform calling convention and callee-save sets;
- unwind directives and object-format expectations;
- runtime symbol ownership formerly supplied by DSOs; and
- cache coherency after code publication.

Do not select Windows x86-64 assembly merely because both targets use PE32+.
Windows SEH, Win32 TLS, process exception handling, and loader APIs are not UEFI
services.

## Memory model

### What UEFI provides

Boot Services allocate and free 4-KiB pages or smaller pool objects. Page
allocation can request any address, a maximum address, or a specific address.
The firmware memory map describes physical ranges and types. These mechanisms
are useful for a firmware `MemMap` backend, but they are not process virtual
memory:

- allocation returns resident addressable memory rather than a sparse reserve;
- there is no standard anonymous/file mapping distinction;
- there are no shared/private mapping aliases;
- there is no portable `MAP_FIXED_NOREPLACE` transaction;
- freeing pages releases the whole allocated range rather than retaining an
  address reservation;
- page protections are not a universally controllable application contract;
  and
- mappings cannot survive `ExitBootServices()` unless the runtime becomes the
  owner of the machine.

UEFI's 4-KiB page size matches ART's minimum page and falls within the current
4-KiB-to-16-KiB page-size-agnostic range in
[`globals.h`](../../vendor/art/libartbase/base/globals.h). This removes one
Wasm mismatch, but not the protection and mapping semantics.

### Low-4-GiB managed heap

All three UEFI targets are 64-bit, while Java heap references remain compressed
32-bit values. The runtime must reserve its complete managed heap below 4 GiB.
`AllocatePages(AllocateMaxAddress, ...)` can request such memory before other
firmware allocations fragment the range, so the requirement is implementable
in principle.

It is not guaranteed. Firmware, device windows, loaded images, and prior boot
allocations may consume the needed low range. Startup must request the entire
bounded heap early, verify that every byte is below 4 GiB, and fail cleanly if
the reservation is unavailable. Falling back to arbitrary 64-bit Java object
addresses would corrupt the managed-reference contract.

The initial memory layout should be explicit:

```text
below 4 GiB:
  managed heap reservation
  compressed-reference-compatible image data, if later admitted

any firmware-allocated address:
  native C/C++ heap
  ART metadata not referenced through compressed Java pointers
  native stacks and TLS blocks
  descriptor/VFS state

firmware-loaded PE sections:
  executable runtime/AOT code
  read-only method metadata and packaged assets
  writable static data
```

### PosixShim mapping rules

| POSIX request | UEFI behavior |
|---|---|
| anonymous `mmap` | Allocate and track 4-KiB pages; honor alignment within explicit limits |
| `munmap` | Free only an owned complete allocation or suballocate from a PosixShim arena |
| `MAP_FIXED` | Permit only inside a pre-owned arena with exact conflict checks; never overwrite firmware memory |
| file mapping | Copy file bytes into owned memory and write back explicitly when supported |
| `mprotect` | Unsupported unless a required, tested memory-attribute capability provides equivalent enforcement |
| `PROT_EXEC` | Unsupported for runtime-created mappings in the baseline |
| guard page | Replace with explicit stack/region bounds checks; do not claim a fault boundary |
| `madvise`, residency, locking | Documented advisory metadata or `ENOSYS`; never silent kernel-equivalent success |

The optional UEFI Memory Attribute Protocol and platform page-table behavior
may be investigated later. They cannot be assumed across firmware, and a
particular OVMF success is not enough to expose `mprotect` or current ART JIT
capabilities in the profile.

## Threads, synchronization, and TLS

Threads are the largest semantic blocker after the hosted C runtime.

Current ART requires:

- Java daemon threads during `Runtime::Start`;
- Java-created threads through `pthread_create`;
- GC, verification, JIT, and runtime worker pools;
- per-thread `Thread::Current()` and JNI state;
- mutexes, reader/writer locks, conditions, timed waits, and thread suspension;
- safepoints and stop-the-world coordination;
- interruption, joining, detachment, and daemon shutdown; and
- stack enumeration for GC, exceptions, and diagnostics.

A single-thread research fork can disable JIT and parallel/concurrent GC,
avoid application thread creation, and replace daemon work with synchronous
calls. That is enough to test DEX parsing, class linking, allocation, GC, JNI,
and switch interpretation. It is not a supported current-ART mode and must not
be enabled by returning success from fake pthread APIs.

A real firmware thread layer would need to define:

1. a required MP Services capability and processor topology;
2. a finite set of usable processor execution contexts, including the BSP;
3. an M:N PosixShim scheduler with independently owned logical thread contexts,
   stacks, TLS blocks, run queues, context switching, and preemption or
   equivalent bounded safepoint scheduling;
4. logical thread creation limited by declared memory/resources rather than
   directly by the AP count;
5. atomics and memory-order behavior for the target architecture;
6. mutex, condition, timed-wait, join, blocking-I/O, and interruption
   semantics integrated with the scheduler;
7. a proven worker-start mechanism despite the post-`ReadyToBoot`
   nonblocking-dispatch restriction;
8. safe BSP marshalling for firmware services that APs may not call;
9. managed thread attachment, suspension, root publication, and GC rendezvous;
10. processor failure and shutdown handling; and
11. a fallback policy that fails admission rather than silently becoming
   single-threaded.

Even a successful MP Services implementation may not be portable enough for a
general UEFI profile. It would need validation on every admitted firmware class
and architecture, not only QEMU.

## Faults, exceptions, and stack walking

### Hardware faults are fatal in the baseline

UEFI does not provide a portable application equivalent of POSIX
`sigaction(SIGSEGV, ..., SA_SIGINFO)` or Windows vectored/structured exception
dispatch. CPU exceptions normally enter firmware or platform handlers. An
application cannot assume it receives a mutable register context or may repair
the PC and resume.

The firmware runtime must therefore disable fault-dependent ART mechanisms:

- implicit null checks;
- signal-based suspend or checkpoint delivery;
- guard-page stack overflow recovery;
- read-barrier or GC schemes requiring protection faults;
- fault-based generated-code probes; and
- native crash recovery that expects signal/SEH chaining.

Java null, bounds, divide, cast, and stack-overflow exceptions must arise from
explicit checks. A hardware access fault, illegal instruction, or corrupted
stack is an unrecoverable firmware-runtime failure. The fatal path should emit
a bounded console/serial diagnostic and return or reset according to an
explicit policy; it must not continue with fabricated state.

### Managed AOT frames can remain walkable

Image-resident quick code has real PCs and can retain method headers and stack
maps. A managed walker can therefore identify compiled methods without the
synthetic-PC machinery required by Wasm. The offline compiler must still
publish exact frame sizes, spill masks, DEX-PC maps, reference maps, and catch
metadata for the chosen firmware quick ABI.

Native C/C++ unwinding is separate. Firmware does not supply Windows
`RtlVirtualUnwind` merely because the file uses PE/COFF. The runtime needs one
of:

- a small project-owned parser/walker for the emitted architecture's PE unwind
  records;
- frame-pointer-based native diagnostics with mechanically enforced compile
  policy; or
- a deliberately limited fatal path that walks only ART-managed frames.

Cross-mode exceptions, JNI frames, and fatal diagnostics must be tested on each
architecture. Full JVMTI compiled-code instrumentation, debugger attach,
deoptimization, OSR, and arbitrary native unwinding remain outside the first
runtime.

## UEFI backend for PosixShim

The complete call stack is:

```text
Java and DEX methods
        |
libcore JNI + ICU/OpenJDK C/C++          statically linked into .efi
        |
libc entrypoints + ART OS abstractions
        |
PosixShim virtual process state          project-owned
        |
versioned UEFI backend
        |
Boot Services / Runtime Services / required protocols
```

PosixShim needs the same three behavior classes used by the WebAssembly
design:

| Class | Meaning |
|---|---|
| Implemented | Sufficiently equivalent for its admitted ART/libcore callers and covered by conformance tests |
| Virtualized | Deterministic, documented firmware personality that differs from a hosted process |
| Unsupported | Returns a documented error or disables the dependent feature before startup |

Correctness-sensitive calls must not be success no-ops. `mprotect`, thread
creation, signal registration, `fsync`, socket options, and executable mapping
are examples where false success can corrupt ART or application state.

### API-area feasibility

| Area | UEFI source | PosixShim judgment |
|---|---|---|
| Native heap | `AllocatePool`/`FreePool` or pages plus a project allocator | Feasible while Boot Services remain |
| Managed heap | Early `AllocatePages` below 4 GiB | Feasible with a bounded heap and fail-closed reservation |
| Files and directories | Simple File System and File Protocol | Feasible subset; UTF-16 paths, volumes, metadata, permissions, links, and atomic rename differ |
| Packaged boot assets | PE read-only section or verified file sidecar | Feasible and should be synchronous before ART startup |
| Console I/O | Simple Text Input/Output, serial, or an owned text sink | Feasible subset; Unicode and buffering need explicit policy |
| Wall clock | `GetTime` | Feasible, subject to firmware quality and timezone semantics |
| Monotonic time and sleep | timer events, `Stall`, monotonic-count service where available | Feasible subset; precision and scheduling differ |
| Entropy | RNG Protocol | Feasible only when the protocol and required algorithm/quality are admitted; otherwise startup failure |
| Descriptors | Project-owned table over files, console, events, and protocol handles | Feasible for a closed resource set |
| Polling | Waitable UEFI events and PosixShim readiness state | Feasible for owned handles at application task priority |
| Logical threads | M:N PosixShim scheduler over owned contexts and a proven processor substrate | Mandatory; MP Services dispatch does not create schedulable threads |
| Mutexes and conditions | Atomics plus the PosixShim scheduler/MP layer | Not supplied by UEFI; must block logical threads rather than consume one AP per waiter |
| TLS | Project-owned per-logical-thread blocks and compiler/runtime hooks | Feasible only after scheduler and context-switch integration |
| Signals | No portable application delivery/context contract | Unsupported |
| Page protection | Optional platform memory-attribute mechanisms | Not a baseline capability |
| Dynamic loading | `LoadImage`/`StartImage` for separate firmware images | Does not implement `dlopen`/`dlsym`; static registries only |
| Process creation | Independent firmware image start/return | Does not implement `fork`, `exec`, pipes, or process groups |
| Environment/identity | load options, variables, synthesized PID/UID/GID/`uname` data | Virtualizable |
| Networking | optional SNP/MNP, TCP4/6, UDP4/6, DNS, DHCP, and HTTP protocols | Curated subset only; token/event model and firmware availability differ from sockets |
| Raw sockets | Link-layer or network protocols on some firmware | No portable POSIX raw-socket contract |
| Persistent variables | Runtime variable services | Suitable for small configuration, not a general filesystem |
| Watchdog | `SetWatchdogTimer` | Must be explicitly managed for a long-running runtime |

### Virtual filesystem and descriptors

Use one project-owned descriptor namespace for ART and all statically linked
libcore/OpenJDK code. Each descriptor records resource kind, access mode,
offset, readiness, ownership, and the underlying UEFI handle or in-memory
object. Candidate kinds are:

- packaged read-only boot DEX/JAR and resources;
- filesystem files and directories;
- in-memory temporary files;
- console input/output and serial logging;
- event/timer objects;
- protocol-backed network endpoints; and
- a small number of firmware variable/configuration handles.

Paths at the Java/POSIX boundary remain UTF-8 under project policy, while the
UEFI backend converts strictly to and from `CHAR16`. There is no current
directory, Unix root, ownership, mode-bit enforcement, symbolic-link model, or
case-sensitivity guarantee unless PosixShim virtualizes it. Java APIs whose
correct behavior cannot be represented must fail explicitly.

Boot DEX/JAR inputs should be available in memory before reduced
`Runtime::Start`. This avoids class loading from callbacks or asynchronous
network protocols and makes the decisive switch-interpreter gate independent
of a particular disk driver.

### Networking is optional platform expansion

UEFI networking protocols use handles, configuration structures, completion
tokens, and events. PosixShim could build blocking `connect`/`send`/`recv`-like
operations by submitting tokens and waiting at application task priority.
That does not make them POSIX sockets:

- protocol availability is optional;
- firmware may expose only some IPv4/IPv6/DNS/DHCP layers;
- option sets, cancellation, readiness, errors, and buffer ownership differ;
- callbacks and waits have task-priority restrictions; and
- long-running throughput and robustness are firmware-dependent.

Networking should not be required for the first ART boot. Each admitted Java
network API needs an exact protocol dependency and conformance gate. A useful
networked Java environment is a later project, not a consequence of linking a
socket shim.

## Static JNI and library surface

The Java `native` keyword still denotes a JNI boundary, but every admitted JNI
implementation is ordinary code inside `art-runtime.efi`. Packaging generates
a registry keyed by library and JNI symbol/class identity. `System.loadLibrary`
may resolve only a predeclared logical library in that registry; it never loads
a firmware image or scans PE symbols.

The initial closure should be smaller than the current complete boot class
path. Include only the Java and JNI functionality needed for:

- object/class/string basics;
- console output;
- deterministic properties and system identity;
- packaged read-only file access;
- clocks and entropy required by startup;
- the selected allocator and collector; and
- the test application.

ICU, Conscrypt/BoringSSL, OpenJDK support, persistent files, networking, and a
broad libcore surface should enter independently. Their static linkability is
not proof that the firmware protocols preserve their semantics.

Application JNI is packaging-time closed world. Arbitrary JNI DSOs, JVMTI
agents, native bridges, plugins, and post-launch symbol lookup are unsupported.

## Freestanding C/C++ runtime requirements

UEFI firmware tables are not a libc. Before ART code can run, the product must
provide and own at least:

- `malloc`/`calloc`/`realloc`/`free` and aligned allocation;
- memory and string functions;
- formatted logging with bounded output;
- errno and error-string policy;
- C++ allocation, guards, static initialization, and termination hooks;
- compiler-rt arithmetic and atomic helpers selected by each architecture;
- a static libc++ subset and any required C++ ABI support;
- TLS hooks for the one-thread bring-up and later real thread model;
- file/descriptor calls consumed by retained libraries;
- clock, entropy, and synchronization entrypoints; and
- a fatal/abort policy that safely returns to firmware or resets.

The product should build freestanding and statically. It must have no PE import
directory naming Windows DLLs, no UCRT dependency, and no hidden dependency on
an EDK II build environment at runtime. EDK II libraries may inform or supply
reviewed source components, but the project-owned PosixShim ABI remains the
observable ART contract.

Static constructors and destructors need a deliberate lifecycle around the
UEFI entrypoint. Returning from `efi_main` should stop the reduced runtime,
release owned Boot Services resources where practical, restore watchdog state,
and report one stable `EFI_STATUS`.

## Target order

### x86-64 first

`uefi-x86_64-posixshim` is the practical research target because:

- Clang/LLD can emit x86-64 COFF/PE;
- OVMF/QEMU provides a fast and inspectable boot loop;
- the repository already has substantial x86-64 PE, ART ABI, low-memory, and
  image-loading experience from Windows;
- ART's x86-64 compiler and interpreter assembly are mature; and
- real x86-64 UEFI hardware is readily available for the required second
  validation environment.

None of the Windows runtime implementation can be assumed. The reuse is in
tooling, object inspection, selected ABI analysis, and perhaps carefully
isolated portable sources.

### AArch64 second

`uefi-aarch64-posixshim` should follow only after the switch-only x86-64
architecture is stable. Its acceptance needs AArch64 OVMF or equivalent
firmware plus real hardware, exact PE relocation and calling-convention tests,
cache-maintenance review, native-stack diagnostics, and independent ART quick
ABI validation. Linux AArch64 success does not admit UEFI AArch64.

### RISC-V64 remains doubly blocked

`uefi-riscv64-posixshim` inherits every runtime/PosixShim blocker and lacks the
required direct Clang COFF emission. The current profile intentionally records
the observed `elf64-littleriscv` output so artifact validation cannot confuse
it with PE32+.

Do not solve this by renaming an ELF file, changing only its suffix, or asking
firmware to load ELF. Acceptable future paths are:

1. upstream LLVM/LLD RISC-V64 COFF and UEFI image support;
2. another trusted, reproducible compiler/linker with a fully specified ABI
   and integration plan; or
3. a reviewed ELF-to-PE conversion pipeline that preserves relocations,
   unwind, symbols needed by ART packaging, and reproducibility.

The third option is itself a significant toolchain project and should not be
the first UEFI milestone.

## Staged validation plan

### Stage 0: toolchain and firmware envelope

- Emit one freestanding x86-64 PE32+ UEFI application with the correct machine,
  subsystem, entrypoint, relocation directory, section permissions, and no
  DLL imports.
- Boot it under pinned QEMU/OVMF and on one real UEFI implementation.
- Record firmware vendor/revision, UEFI revision, Secure Boot state, memory
  map, required protocols, and watchdog behavior without putting those values
  in the canonical target ID.
- Prove `EFIAPI` direct and indirect calls with scalar, pointer, structure,
  variadic, and callback boundaries.
- Validate pool/page allocation, below-4-GiB `AllocateMaxAddress`, timer waits,
  console/serial output, and clean return to firmware.
- Establish a shell-free Clang/LLD build through the common Python frontend or
  an explicitly research-only harness. Do not enable the blocked product
  profile yet.

This stage validates only the execution envelope, not ART.

### Stage 1: freestanding runtime and PosixShim core

- Link compiler-rt, the selected static C/C++ runtime, allocator, logging, and
  fatal handling into one image.
- Freeze PosixShim ABI version 1 and inventory exact POSIX/libc calls in the
  selected `libartbase`, DEX, runtime, libcore, ICU/OpenJDK, and JNI closure.
- Implement descriptor state, packaged read-only files, console, wall and
  monotonic clocks, timers, entropy, environment/system identity, and page
  allocation.
- Classify every inventoried call as implemented, virtualized, or unsupported.
- Add negative gates proving signals, dynamic loading, process creation,
  executable mappings, and unsupported page protection fail explicitly.
- Reserve the complete configured Java heap below 4 GiB before substantial
  firmware allocation.

### Stage 2: switch-only ART research fork

- Build `libartbase`, DEX parsing/verifying, class linking, the selected
  collector, and the C++ switch interpreter for x86-64 UEFI.
- Add a one-thread `Thread::Current()` and TLS implementation.
- Replace daemon-thread startup and asynchronous runtime work with explicit
  single-thread research hooks; record every semantic removal.
- Disable nterp, mterp, JIT, OSR, deoptimization, dynamic agents, implicit
  faults, boot image loading, and compiled-code JVMTI.
- Package the minimum boot DEX/JAR and statically linked JNI closure.
- Boot imageless and run `HelloWorld` through the switch interpreter.
- Prove allocation, collection, Java exceptions, reflection basics, and stack
  traces without hardware fault recovery.

This is the decisive feasibility gate. Passing it does not change the
canonical target's support status.

### Stage 3: image-resident offline AOT

- Refactor or adapt the offline compiler output into linkable UEFI quick-code
  and metadata sections.
- Bind every compiled method to exact DEX and boot-class-path hashes.
- Link all AOT code into `art-runtime.efi`; do not allocate executable memory
  at runtime.
- Exercise interpreter-to-AOT, AOT-to-interpreter, direct/static AOT calls,
  virtual/interface dispatch, JNI calls, exceptions, GC roots, and stack
  walking.
- Validate PE base relocation and randomized image load addresses.
- Reject corrupted metadata, wrong DEX hashes, overlapping code ranges, and
  out-of-image entrypoints.
- Sign the final image after AOT linkage and repeat under an enabled Secure
  Boot test configuration.

### Stage 4: threading decision

- Decide whether the product is permanently a new single-thread runtime or
  attempts a real ART thread contract.
- For the latter, implement an M:N PosixShim scheduler whose logical thread
  capacity is independent of the finite AP count. It must own contexts, stacks,
  TLS, run queues, context switching, synchronization, blocking/wakeup, and BSP
  firmware-call marshalling.
- Prove the scheduler's execution substrate despite the post-`ReadyToBoot`
  restriction on nonblocking MP Services dispatch; do not infer persistent AP
  workers from protocol presence.
- Run more simultaneously live Java threads than enabled processors through
  creation, monitor, wait/notify, interruption, joining, daemon, GC rendezvous,
  blocking-I/O, and fatal-shutdown stress.
- Test loss or partial availability of application processors and fail closed.
- Validate both emulated firmware and real machines for every admitted
  architecture.

Without this stage, the project remains a useful restricted runtime but cannot
admit a canonical current-ART UEFI profile.

### Stage 5: optional platform expansion

- Add persistent filesystem behavior one API family at a time.
- Add broader libcore and ICU with exact resource and Unicode tests.
- Add networking only behind declared protocol requirements and socket-behavior
  conformance tests.
- Add AArch64 as a new exact target with independent build/runtime evidence.
- Reassess external executable artifacts or memory-attribute capabilities only
  as separately gated research; do not infer JIT support.

## Acceptance requirements

### Build and artifact gates

- The blocked canonical profile remains rejected until a reviewed status
  change; research builds cannot silently mark it experimental.
- Every build uses one exact target profile and an isolated output tree.
- Clang GNU-style drivers and LLD emit the target image; no GCC, MSVC, MinGW,
  Visual Studio generator, shell build logic, or direct untracked linker path
  is introduced.
- LLVM inspection confirms PE32+, exact machine architecture, UEFI application
  subsystem, image entrypoint, base relocations, section permissions, and no
  DLL imports.
- The image contains no unresolved hosted-OS symbols, import libraries, or
  ELF executable payload represented as UEFI code.
- All executable method ranges lie inside firmware-loaded executable PE
  sections and are covered by the signed image.
- Generated profiles, graphs, and manifests contain no machine path and retain
  the canonical target ID and PosixShim ABI version.
- `uefi-riscv64-posixshim` continues to report both the ART-contract and COFF
  blockers until real PE output is mechanically inspected.

### Runtime gates

- The same image boots under pinned OVMF and at least one real firmware
  implementation for its architecture.
- Startup validates required protocols and reports a bounded diagnostic for
  each missing capability.
- The complete managed heap reservation is below 4 GiB and survives allocation
  and GC stress.
- Boot succeeds without UEFI Shell protocols, environment conventions, or
  filesystem current-directory assumptions.
- Packaged DEX/JAR identities are verified before parsing.
- Switch-interpreted Hello, explicit Java exceptions, JNI console output,
  allocation/GC, and orderly shutdown pass without a hardware fault.
- Unsupported `fork`, `exec`, signals, dynamic loading, page protection, and
  executable mappings return their documented errors rather than success.
- Hardware faults are treated as fatal and are never reported as recovered
  Java exceptions.
- Long-running tests explicitly manage the firmware watchdog and restore or
  document final state.
- No test calls `ExitBootServices()` unless it belongs to a separate kernel
  experiment.

### AOT gates

- Every AOT entrypoint and metadata range is inside the linked PE image.
- DEX, boot-class-path, compiler, target, and PosixShim ABI mismatches are
  rejected before method dispatch.
- AOT and switch executions produce matching results for a differential method
  suite.
- GC can enumerate precise roots through mixed interpreted/AOT/JNI frames.
- Exceptions and stack traces cross all mixed-mode boundaries.
- Relocated image bases do not change behavior or invalidate PC-to-method
  lookup.
- Secure Boot validation covers the final AOT-linked image, not an earlier
  switch-only binary.

## Expected scale

These are rough orders of magnitude, not a staffing schedule:

- UEFI Clang/LLD envelope, object inspection, QEMU/OVMF harness, and minimal
  freestanding C runtime: roughly 1-3 engineer-months;
- exact POSIX inventory plus boot-critical PosixShim memory, descriptors,
  packaged files, console, clocks, timers, entropy, and negative behavior:
  roughly 3-9 engineer-months;
- `libartbase`, DEX, class linking, collector, static JNI, and imageless
  switch-interpreter Hello in a one-thread research fork: roughly 9-18
  engineer-months;
- image-resident offline AOT, link metadata, mixed-mode GC/exceptions, and
  Secure Boot validation after switch boot works: another 6-18
  engineer-months;
- a credible M:N pthread/Java scheduler over a proven firmware processor
  substrate: another 12-24 engineer-months, with substantial risk that standard
  post-`ReadyToBoot` MP Services is insufficient;
- broader libcore, ICU, persistent files, networking, diagnostics, and a second
  architecture: likely multiple engineer-years in total; and
- current ART parity with native DSO topology, dynamic JNI, signals/faults,
  JIT/OSR, full JVMTI, and post-`ExitBootServices()` operation: no credible UEFI
  implementation path under the present platform contract.

The ranges overlap. Existing ART ISA backends save compiler work relative to
Wasm, but they do not reduce the freestanding runtime, threading, memory,
fault, PosixShim, firmware-quality, or platform-validation effort.

## Final recommendation

Keep all three UEFI profiles at `impossible_under_current_art_contract`.
Do not add a `PlatformUefi.cmake` branch that converts DSOs to static libraries
and stubs unsupported calls merely to make compilation advance.

If research is funded, use this progression:

1. start with `uefi-x86_64-posixshim` under pinned QEMU/OVMF and one real
   firmware implementation;
2. remain entirely before `ExitBootServices()`;
3. build one freestanding, statically linked, import-free PE32+ application;
4. implement and version the project-owned PosixShim over exact UEFI
   capabilities;
5. reserve the complete Java heap below 4 GiB at startup;
6. establish an imageless C++ switch interpreter and static JNI registry in an
   explicitly single-thread research fork;
7. add selective physical-ISA AOT only as code linked into the signed `.efi`
   image;
8. keep current OAT loading, native DSOs, dynamic JNI, JIT, OSR,
   deoptimization, implicit-fault handling, and compiled-code JVMTI disabled;
9. treat an M:N PosixShim scheduler, with logical thread capacity independent
   of AP count, as mandatory before any claim of current-ART target admission;
10. validate AArch64 independently after x86-64; and
11. leave RISC-V64 blocked until a mechanically verified COFF/PE toolchain path
    exists.

If the intended system must call `ExitBootServices()` and continue as a
general Java environment, build or select an operating system and port native
ART to that operating system. Calling such a kernel an ART UEFI profile would
hide the most important architectural boundary.

## Upstream references

- [UEFI Specification 2.11](https://uefi.org/specs/UEFI/2.11/)
- [UEFI specifications and errata](https://uefi.org/specifications)
- [UEFI Boot Services](https://uefi.org/specs/UEFI/2.11/07_Services_Boot_Services.html)
- [UEFI Runtime Services](https://uefi.org/specs/UEFI/2.11/08_Services_Runtime_Services.html)
- [UEFI protocols](https://uefi.org/specs/UEFI/2.11/12_Protocols_Console_Support.html)
- [Platform Initialization Specification](https://uefi.org/specs/PI/1.8/)
- [EDK II MP Services Protocol contract](https://github.com/tianocore/edk2/blob/master/MdePkg/Include/Protocol/MpService.h)
- [TianoCore EDK II](https://github.com/tianocore/edk2)
- [TianoCore OVMF package](https://github.com/tianocore/edk2/tree/master/OvmfPkg)
- [LLVM code generator target support](https://llvm.org/docs/CodeGenerator.html)
- [LLD PE/COFF support](https://lld.llvm.org/windows_support.html)
- [QEMU system-emulation documentation](https://www.qemu.org/docs/master/system/index.html)
