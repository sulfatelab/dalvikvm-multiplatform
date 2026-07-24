# Win64 pthread_once concurrency result

Date: 2026-07-24. VM: agent01. Runtime: Wine 10.0. Build:
`build/win64_phase1` RelWithDebInfo.

## Finding

The compatibility `pthread_once` implementation used a single
`InterlockedCompareExchange` from 0 to 1. The winning thread set 1 before
running the initializer, while losing threads returned immediately instead of
waiting for initialization to finish.

The final JIT matrix exposed this as an intermittent NetProbe abort. The main
and client threads could concurrently make the first
`AFileDescriptor_getFd()` call during socket close. One thread entered
`JniConstants` initialization while the other observed the once flag and then
used the still-null cached `FileDescriptor.descriptor` field ID:

```text
JNI DETECTED ERROR IN APPLICATION: fid == null
in call to art::JNI<false>::GetIntField
from void libcore.io.AsynchronousCloseMonitor.signalBlockedThreads(java.io.FileDescriptor)
```

This was independent of the CriticalNative ABI changes. Ten `-Xint` NetProbe
controls passed; JIT scheduling made the existing initialization race easier to
hit.

## Fix

`pthread_once` now has three states:

1. uninitialized;
2. initializing;
3. initialized.

The winning thread runs the initializer and publishes state 3 with an
interlocked exchange. Other threads yield until they observe state 3, so no
caller returns while initialization is incomplete. The public
`pthread_once_t` representation remains a `LONG`.

No runtime workaround or NetProbe warm-up was added.

## Verification

The permanent stress probe starts 32 Windows threads simultaneously. Its
initializer deliberately sleeps before publishing a value, making the former
early-return behavior directly observable.

```sh
REPEATS=10 bash tools/verify/win64_phase4/run_pthread_once_probe.sh
```

Result:

```text
pthread_once acceptance: 10/10
```

Additional final-binary verification:

- JIT-enabled NetProbe repeated 10/10;
- CriticalNative combined acceptance: dual 10/10 and J-1 10/10 process runs;
- default compiled-JNI/FastNative 7/7 checks pass;
- JIT smoke 12/12;
- JIT matrix 14/14.
