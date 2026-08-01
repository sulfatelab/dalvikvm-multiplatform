# Windows JIT runtime controls

The exact `windows-x86_64-msvc` gate owns the supported JIT control surface
without Bash, Wine, or a Phase-1 staging tree. Seven isolated Hello processes
cover default verbose compilation, the ignored retired J-1 opt-out, the
Windows compile-disable environment switch, `-Xusejit:false`, filter, exclude,
and quiet diagnostics. Five additional threshold-zero processes run the
canonical Math CriticalNative, file I/O, loopback network, GC, and uncaught
exception workloads.

Each process receives a fresh runtime/data/ICU/temp layout below the target
output. The aggregate JSON contains names, counts, hashes, and marker results,
but no machine absolute paths. Dumps and symlink/reparse paths are forbidden.

The former Phase-4 smoke and matrix scripts are historical evidence only. Ten
of their small managed jars no longer have source in the repository; their ABI
purpose is covered more deeply by unified W-002/W-003, while this gate keeps
the product control contract and the five canonical application workloads.

Windows Server 2025 x86-64 passed the expanded W-025 stage 9/9 twice. The new
gate completed its seven controls and five workloads in 12.10 and 12.17
seconds; both successful stage builds reported `ninja: no work to do`. The
Linux-hosted Windows cross stage built the full dependency closure, passed the
source/PE reviewer, and repeated as a Ninja no-op.
