    .text
    .globl Win32ImplicitStackProbe
    .def Win32ImplicitStackProbe
    .scl 2
    .type 32
    .endef
    .p2align 4, 0x90
    .seh_proc Win32ImplicitStackProbe
Win32ImplicitStackProbe:
    .seh_endprologue
    .globl Win32ImplicitStackProbeInstruction
Win32ImplicitStackProbeInstruction:
    testq %rax, -8192(%rsp)
    retq
    .seh_endproc

    .globl Win32PregrowStack
    .def Win32PregrowStack
    .scl 2
    .type 32
    .endef
    .p2align 4, 0x90
    .seh_proc Win32PregrowStack
Win32PregrowStack:
    .seh_endprologue
    movq %rsp, %r8
    andq $-4096, %r8
    xorl %eax, %eax
.Lpregrow_next:
    subq $4096, %r8
    cmpq %rcx, %r8
    jb .Lpregrow_done
    movb (%r8), %r9b
    incl %eax
    cmpq %rcx, %r8
    ja .Lpregrow_next
.Lpregrow_done:
    retq
    .seh_endproc
