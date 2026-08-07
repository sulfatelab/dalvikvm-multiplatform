/*
 * Copyright (C) 2026 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

// Mark this object as containing CFG-instrumented indirect calls.
        .def    @feat.00;
        .scl    3;
        .type   0;
        .endef
        .globl  @feat.00
@feat.00 = 2048

        .text
        .def    w032_guarded_invoke_static;
        .scl    2;
        .type   32;
        .endef
        .globl  w032_guarded_invoke_static
        .p2align 4

// uint64_t w032_guarded_invoke_static(ArtMethod* method, Thread* self,
//                                     const void* target, uint32_t first_arg)
//
// Establish the no-reference static quick-invoke frame, preserve the Microsoft
// x64 nonvolatile state that ART quick code may use, and enter the exact OAT
// target through the operating system's CFG dispatch pointer. The first quick
// integer argument is carried in ESI; a no-argument JNI stub ignores it.
w032_guarded_invoke_static:
        .seh_proc w032_guarded_invoke_static
        pushq   %rbp
        .seh_pushreg %rbp
        pushq   %rdi
        .seh_pushreg %rdi
        pushq   %rsi
        .seh_pushreg %rsi
        pushq   %rbx
        .seh_pushreg %rbx
        pushq   %r12
        .seh_pushreg %r12
        pushq   %r13
        .seh_pushreg %r13
        pushq   %r14
        .seh_pushreg %r14
        pushq   %r15
        .seh_pushreg %r15
        subq    $184, %rsp
        .seh_stackalloc 184
        movdqu  %xmm6, 0(%rsp)
        .seh_savexmm %xmm6, 0
        movdqu  %xmm7, 16(%rsp)
        .seh_savexmm %xmm7, 16
        movdqu  %xmm8, 32(%rsp)
        .seh_savexmm %xmm8, 32
        movdqu  %xmm9, 48(%rsp)
        .seh_savexmm %xmm9, 48
        movdqu  %xmm10, 64(%rsp)
        .seh_savexmm %xmm10, 64
        movdqu  %xmm11, 80(%rsp)
        .seh_savexmm %xmm11, 80
        movdqu  %xmm12, 96(%rsp)
        .seh_savexmm %xmm12, 96
        movdqu  %xmm13, 112(%rsp)
        .seh_savexmm %xmm13, 112
        movdqu  %xmm14, 128(%rsp)
        .seh_savexmm %xmm14, 128
        movdqu  %xmm15, 144(%rsp)
        .seh_savexmm %xmm15, 144
        .seh_endprologue

        movq    %rcx, %rdi
        movq    %rdx, %r15
        movq    %r8, %r12
        movl    %r9d, %esi
        movq    $0, 160(%rsp)
        leaq    160(%rsp), %rsp
        movq    %r12, %rax
        movq    __guard_dispatch_icall_fptr(%rip), %r10
        callq   *%r10
        subq    $160, %rsp

        movdqu  0(%rsp), %xmm6
        movdqu  16(%rsp), %xmm7
        movdqu  32(%rsp), %xmm8
        movdqu  48(%rsp), %xmm9
        movdqu  64(%rsp), %xmm10
        movdqu  80(%rsp), %xmm11
        movdqu  96(%rsp), %xmm12
        movdqu  112(%rsp), %xmm13
        movdqu  128(%rsp), %xmm14
        movdqu  144(%rsp), %xmm15
        addq    $184, %rsp
        popq    %r15
        popq    %r14
        popq    %r13
        popq    %r12
        popq    %rbx
        popq    %rsi
        popq    %rdi
        popq    %rbp
        retq
        .seh_endproc

        .addrsig
        .addrsig_sym __guard_dispatch_icall_fptr
