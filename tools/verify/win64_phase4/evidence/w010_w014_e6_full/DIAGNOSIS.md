# W-010/W-014 E6 complete native host result

**Host:** Windows Server 2025 Datacenter Evaluation, build 26100, x86_64  
**Run date:** 2026-07-28  
**Package SHA-256:** `9ab66c9a7b2e8e40210f9c47971cbf5ac9f86c0ca729c25a05448f12346499bc`  
**Raw result bundle SHA-256:** `d6bb85c1529496cb384bebcc1495378ade0e253041e01a9605f3f6c90b8538e5`  
**Raw result bundle bytes:** `24378237`  
**Root revision:** `6cce29d7b5f1647b90c56ad02de747fdebcdca99`  
**ART revision:** `bbb397f2deff19b80588716ee53b0eaf1ab9db88`

The archive was transferred to a fresh directory and matched the Linux
SHA-256 before extraction. The runner passed package integrity and the
structural report. The returned identity files and complete issued payload
match the issued package. The Python reviewer reaches the result check and
correctly rejects it because `RESULT_W010_W014.txt` ends in `OVERALL FAIL`.

The runner records 25 of the required 30 PASS rows. It accepts:

- Windows build 26100, package identity, structural report, disabled HSP, and
  zero named incompatible CET fields;
- static/live unwind, including two interpreter-bridge records;
- two nterp, two switch, and two JIT XMM6-XMM15 runs;
- thread reservation/lifetime, stack-page, fault-record, sigchain/frame-SEH,
  and started-runtime no-chain rejection;
- nterp and threshold-zero JIT NPE delivery; and
- all five fatal origins: static `-Xint`, JIT J-2/J-1, and OSR J-2/J-1.

Each fatal case enters VEH and UEF, terminates with `0xC0000005`, and writes a
new named 14-stream minidump:

```text
745501  6b905742f5b9418db0da8462cce71744bb2113089574c03407768bc6665c33d7  static
742251  fbe7b7f660273d5452900530d299a07214b8c1c2e0e52a772a35a037eba1f33d  jit-j2
745867  f1dbc6d200a865964036007ad2ba1dd7706e76285fe47b25674c06e8c17dfcd2  jit-j1
748977  b9fb23d0a64ce605a3166599cfb666be4d28d02fe1a5103cc028caa97947cbe5  osr-j2
747553  1edc97f5f5750ecb28da496063158c12e1af6129bb49184462ce0ea808817c95  osr-j1
```

The five missing PASS rows are the three managed-SOE cases and the two
handled-fault aggregates:

```text
switch_so  exit=0xC0000005  fixed-page state rejected with error=13
nterp_so   exit=0xC00000FD  VEH only, no managed recovery
jit_so     exit=0xC00000FD  VEH, UEF, and unwanted minidump
```

The JIT SOE dump is a valid 1,768,325-byte 14-stream `MDMP` with SHA-256
`cc4cb881901d108bb380fb59c8d0ccccfc90c87c96c7ca0ed50229f51681864c`.
Its presence causes the handled-dump scan to fail; the diagnostic markers in
the three SOE logs cause the handled-log scan to fail. Those are consequences,
not independent regressions.

This run natively accepts the repaired five-origin fatal-dispatch matrix. It
does not accept W-014: the next product stage is a managed-SOE delivery design
that does not require a fixed `PAGE_NOACCESS` page to survive Windows stack
growth, followed by the repaired 30-record runner.
