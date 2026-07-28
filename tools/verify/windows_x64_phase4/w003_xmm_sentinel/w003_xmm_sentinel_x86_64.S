    .text
    .globl W003XmmSentinelAssembly
    .def W003XmmSentinelAssembly
    .scl 2
    .type 32
    .endef
    .p2align 4, 0x90
    .seh_proc W003XmmSentinelAssembly
W003XmmSentinelAssembly:
    // 32-byte Microsoft shadow space, 160-byte native XMM save area, and
    // 8 bytes for the expected result/self-test flag while retaining alignment.
    subq $200, %rsp
    .seh_stackalloc 200
    movdqu %xmm6, 32(%rsp)
    .seh_savexmm %xmm6, 32
    movdqu %xmm7, 48(%rsp)
    .seh_savexmm %xmm7, 48
    movdqu %xmm8, 64(%rsp)
    .seh_savexmm %xmm8, 64
    movdqu %xmm9, 80(%rsp)
    .seh_savexmm %xmm9, 80
    movdqu %xmm10, 96(%rsp)
    .seh_savexmm %xmm10, 96
    movdqu %xmm11, 112(%rsp)
    .seh_savexmm %xmm11, 112
    movdqu %xmm12, 128(%rsp)
    .seh_savexmm %xmm12, 128
    movdqu %xmm13, 144(%rsp)
    .seh_savexmm %xmm13, 144
    movdqu %xmm14, 160(%rsp)
    .seh_savexmm %xmm14, 160
    movdqu %xmm15, 176(%rsp)
    .seh_savexmm %xmm15, 176
    .seh_endprologue

    movl %r9d, 192(%rsp)
    movzbl 240(%rsp), %r10d
    movl %r10d, 196(%rsp)
    movdqu g_w003_xmm_patterns(%rip), %xmm6
    movdqu g_w003_xmm_patterns+16(%rip), %xmm7
    movdqu g_w003_xmm_patterns+32(%rip), %xmm8
    movdqu g_w003_xmm_patterns+48(%rip), %xmm9
    movdqu g_w003_xmm_patterns+64(%rip), %xmm10
    movdqu g_w003_xmm_patterns+80(%rip), %xmm11
    movdqu g_w003_xmm_patterns+96(%rip), %xmm12
    movdqu g_w003_xmm_patterns+112(%rip), %xmm13
    movdqu g_w003_xmm_patterns+128(%rip), %xmm14
    movdqu g_w003_xmm_patterns+144(%rip), %xmm15

    call W003InvokeManagedCallback

    cmpl $0, 196(%rsp)
    je .Lself_test_done
    pxor %xmm6, %xmm6
    pxor %xmm7, %xmm7
    pxor %xmm8, %xmm8
    pxor %xmm9, %xmm9
    pxor %xmm10, %xmm10
    pxor %xmm11, %xmm11
    pxor %xmm12, %xmm12
    pxor %xmm13, %xmm13
    pxor %xmm14, %xmm14
    pxor %xmm15, %xmm15
.Lself_test_done:
    xorl %r11d, %r11d
    cmpl 192(%rsp), %eax
    je .Lcallback_ok
    orl $1024, %r11d
.Lcallback_ok:
    movdqu g_w003_xmm_patterns(%rip), %xmm0
    pcmpeqb %xmm0, %xmm6
    pmovmskb %xmm6, %r10d
    cmpl $65535, %r10d
    je .Lxmm6_ok
    orl $1, %r11d
.Lxmm6_ok:
    movdqu g_w003_xmm_patterns+16(%rip), %xmm0
    pcmpeqb %xmm0, %xmm7
    pmovmskb %xmm7, %r10d
    cmpl $65535, %r10d
    je .Lxmm7_ok
    orl $2, %r11d
.Lxmm7_ok:
    movdqu g_w003_xmm_patterns+32(%rip), %xmm0
    pcmpeqb %xmm0, %xmm8
    pmovmskb %xmm8, %r10d
    cmpl $65535, %r10d
    je .Lxmm8_ok
    orl $4, %r11d
.Lxmm8_ok:
    movdqu g_w003_xmm_patterns+48(%rip), %xmm0
    pcmpeqb %xmm0, %xmm9
    pmovmskb %xmm9, %r10d
    cmpl $65535, %r10d
    je .Lxmm9_ok
    orl $8, %r11d
.Lxmm9_ok:
    movdqu g_w003_xmm_patterns+64(%rip), %xmm0
    pcmpeqb %xmm0, %xmm10
    pmovmskb %xmm10, %r10d
    cmpl $65535, %r10d
    je .Lxmm10_ok
    orl $16, %r11d
.Lxmm10_ok:
    movdqu g_w003_xmm_patterns+80(%rip), %xmm0
    pcmpeqb %xmm0, %xmm11
    pmovmskb %xmm11, %r10d
    cmpl $65535, %r10d
    je .Lxmm11_ok
    orl $32, %r11d
.Lxmm11_ok:
    movdqu g_w003_xmm_patterns+96(%rip), %xmm0
    pcmpeqb %xmm0, %xmm12
    pmovmskb %xmm12, %r10d
    cmpl $65535, %r10d
    je .Lxmm12_ok
    orl $64, %r11d
.Lxmm12_ok:
    movdqu g_w003_xmm_patterns+112(%rip), %xmm0
    pcmpeqb %xmm0, %xmm13
    pmovmskb %xmm13, %r10d
    cmpl $65535, %r10d
    je .Lxmm13_ok
    orl $128, %r11d
.Lxmm13_ok:
    movdqu g_w003_xmm_patterns+128(%rip), %xmm0
    pcmpeqb %xmm0, %xmm14
    pmovmskb %xmm14, %r10d
    cmpl $65535, %r10d
    je .Lxmm14_ok
    orl $256, %r11d
.Lxmm14_ok:
    movdqu g_w003_xmm_patterns+144(%rip), %xmm0
    pcmpeqb %xmm0, %xmm15
    pmovmskb %xmm15, %r10d
    cmpl $65535, %r10d
    je .Lxmm15_ok
    orl $512, %r11d
.Lxmm15_ok:

    movdqu 32(%rsp), %xmm6
    movdqu 48(%rsp), %xmm7
    movdqu 64(%rsp), %xmm8
    movdqu 80(%rsp), %xmm9
    movdqu 96(%rsp), %xmm10
    movdqu 112(%rsp), %xmm11
    movdqu 128(%rsp), %xmm12
    movdqu 144(%rsp), %xmm13
    movdqu 160(%rsp), %xmm14
    movdqu 176(%rsp), %xmm15
    movl %r11d, %eax
    addq $200, %rsp
    retq
    .seh_endproc
