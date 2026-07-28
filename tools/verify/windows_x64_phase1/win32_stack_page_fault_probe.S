    .text
    .globl Win32StackPageFaultRead
    .def Win32StackPageFaultRead
    .scl 2
    .type 32
    .endef
    .p2align 4, 0x90
    .seh_proc Win32StackPageFaultRead
Win32StackPageFaultRead:
    .seh_endprologue
    .globl Win32StackPageFaultInstruction
Win32StackPageFaultInstruction:
    movzbl (%rcx), %eax
    .globl Win32StackPageFaultResume
Win32StackPageFaultResume:
    retq
    .seh_endproc
