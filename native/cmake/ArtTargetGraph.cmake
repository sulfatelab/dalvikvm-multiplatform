# Load the target-resolved generated graph and apply reviewed OS-boundary
# source/topology augmentations. This common include is not an entry point.

include("${ART_GRAPH_FILE}")

if(TARGET art-compiler)
    get_target_property(_art_compiler_type art-compiler TYPE)
    if(NOT _art_compiler_type STREQUAL "SHARED_LIBRARY")
        message(FATAL_ERROR "ART requires art-compiler to be a SHARED target")
    endif()
else()
    message(FATAL_ERROR "Generated ART graph must define the shared art-compiler target")
endif()

if(ART_TARGET_PLATFORM STREQUAL "windows")
    set(_art_windows_runtime "${MDVM_ART_ROOT_DIR}/art/runtime/multiplatform/windows")
    set(_art_windows_openjdk "${MDVM_ART_ROOT_DIR}/art/openjdkjvm")
    # Java's platform library-name mapping uses the Android product sonames,
    # including the `lib` prefix on PE. Keep the three TLS DSOs identical to
    # their ELF names instead of accepting CMake's prefix-less Windows default.
    foreach(_art_tls_target crypto ssl javacrypto)
        if(TARGET ${_art_tls_target})
            set_target_properties(${_art_tls_target} PROPERTIES PREFIX "lib")
        endif()
    endforeach()
    if(TARGET procinfo)
        target_sources(procinfo PRIVATE "${_repo}/compat/src/windows_procinfo_stub.cc")
    endif()
    if(TARGET dexfile)
        target_sources(dexfile PRIVATE
            "${MDVM_ART_ROOT_DIR}/art/libdexfile/external/dex_file_ext.cc"
            "${MDVM_ART_ROOT_DIR}/art/libdexfile/external/dex_file_supp.cc")
    endif()
    if(TARGET unwindstack)
        target_sources(unwindstack PRIVATE
            "${MDVM_ART_ROOT_DIR}/art/multiplatform/windows/AsmGetRegs_stub.c")
    endif()
    foreach(_art_cpu_target cpu_features art dex2oat_static)
        if(TARGET ${_art_cpu_target})
            target_sources(${_art_cpu_target} PRIVATE
                "${MDVM_ART_ROOT_DIR}/external/cpu_features/src/impl_x86_windows.c")
        endif()
    endforeach()
    if(TARGET artbase)
        target_link_libraries(artbase onecore)
    endif()
    if(TARGET art)
        target_sources(art PRIVATE
            "${_art_windows_runtime}/thread_windows.cc"
            "${_art_windows_runtime}/stack_windows.cc"
            "${_art_windows_runtime}/cet_compat.cc"
            "${_art_windows_runtime}/jit_unwind_windows.cc"
            "${_art_windows_runtime}/runtime_windows.cc"
            "${_art_windows_runtime}/monitor_windows.cc"
            "${_art_windows_openjdk}/openjdkjvm_memory_windows.cc")
        set(_art_x86_64_asm_support_deps
            "${MDVM_ART_ROOT_DIR}/art/runtime/arch/x86_64/asm_support_x86_64.S"
            "${MDVM_ART_ROOT_DIR}/art/runtime/arch/x86_64/asm_support_x86_64.h"
            "${MDVM_ART_ROOT_DIR}/art/runtime/interpreter/cfi_asm_support.h"
            "${MDVM_ART_ROOT_DIR}/art/runtime/asm_support.h")
        set_property(SOURCE
            "${MDVM_ART_ROOT_DIR}/art/runtime/arch/x86_64/memcmp16_x86_64.S"
            "${MDVM_ART_ROOT_DIR}/art/runtime/arch/x86_64/native_entrypoints_x86_64.S"
            "${MDVM_ART_ROOT_DIR}/art/runtime/arch/x86_64/jni_entrypoints_x86_64.S"
            "${MDVM_ART_ROOT_DIR}/art/runtime/arch/x86_64/quick_entrypoints_x86_64.S"
            "${MDVM_GENSRC_DIR}/art/asm/mterp/${ART_TARGET_MTERP_OUTPUT}"
            APPEND PROPERTY OBJECT_DEPENDS "${_art_x86_64_asm_support_deps}")
    endif()
    if(TARGET openjdkjvm)
        target_sources(openjdkjvm PRIVATE
            "${_repo}/compat/src/windows_x64_socket_posix.c"
            "${_repo}/compat/src/windows_x64_socket_fd_registry.c")
        if(TARGET javacore)
            target_link_libraries(javacore openjdkjvm)
        endif()
    endif()
    if(TARGET javacore)
        target_sources(javacore PRIVATE
            "${MDVM_LIBCORE_DIR}/multiplatform/windows/native/register_libcore_io_Linux_win.cpp"
            "${MDVM_LIBCORE_DIR}/multiplatform/windows/native/AsynchronousCloseMonitor_win.cpp"
            "${MDVM_LIBCORE_DIR}/multiplatform/windows/native/android_system_OsConstantsHolder_win.cpp"
            "${_repo}/tools/windows_x64/jni_stubs/win_path.c"
            "${_repo}/tools/windows_x64/jni_stubs/win_fs_natives.c"
            "${_repo}/tools/windows_x64/jni_stubs/win_net_natives.c"
            "${_repo}/tools/windows_x64/jni_stubs/libcore_hello3.c")
        target_include_directories(javacore BEFORE PRIVATE
            "${MDVM_LIBCORE_DIR}/multiplatform/windows/native"
            "${MDVM_LIBCORE_DIR}/luni/src/main/native"
            "${_repo}/tools/windows_x64/jni_stubs")
        target_compile_definitions(javacore PRIVATE MDVM_SOCKET_FD_TRACKING=1)
        target_link_libraries(javacore openjdkjvm icuuc icui18n)
    endif()
    if(TARGET openjdk)
        target_sources(openjdk PRIVATE
            "${MDVM_LIBCORE_DIR}/multiplatform/windows/native/openjdk_OnLoad_win.cpp"
            "${MDVM_LIBCORE_DIR}/multiplatform/windows/native/win_close.cpp"
            "${MDVM_LIBCORE_DIR}/multiplatform/windows/native/NativeThread_win.c"
            "${MDVM_LIBCORE_DIR}/multiplatform/windows/native/AsynchronousCloseMonitor_win.cpp"
            "${_repo}/tools/windows_x64/jni_stubs/win_runtime_natives.c"
            "${_repo}/tools/windows_x64/jni_stubs/libcore_hello3.c"
            "${_repo}/tools/windows_x64/jni_stubs/win_process_natives.c"
            "${_repo}/compat/src/openjdk_excluded_registers_windows.cc")
        target_include_directories(openjdk BEFORE PRIVATE
            "${MDVM_LIBCORE_DIR}/multiplatform/windows/native"
            "${MDVM_LIBCORE_DIR}/luni/src/main/native"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native"
            "${_repo}/tools/windows_x64/jni_stubs")
        set(_art_windows_openjdk_linuxish_c
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/FileDispatcherImpl.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/FileChannelImpl.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/IOUtil.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/Net.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/net_util_md.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/net_util.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/EPoll.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/SocketChannelImpl.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/ServerSocketChannelImpl.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/DatagramChannelImpl.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/DatagramDispatcher.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/PollArrayWrapper.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/FileKey.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/MappedByteBuffer.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/FileInputStream.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/io_util_md.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/SocketInputStream.c"
            "${MDVM_LIBCORE_DIR}/ojluni/src/main/native/SocketOutputStream.c")
        set_source_files_properties(${_art_windows_openjdk_linuxish_c}
            PROPERTIES COMPILE_DEFINITIONS "__linux__=1;MDVM_SOCKET_FD_TRACKING=1")
        target_link_libraries(openjdk openjdkjvm icuuc)
    endif()
    if(TARGET javacore OR TARGET openjdk)
        set_source_files_properties(
            "${_repo}/tools/windows_x64/jni_stubs/libcore_hello3.c"
            PROPERTIES COMPILE_DEFINITIONS
                "JNI_OnLoad=mdvm_stub_JNI_OnLoad_unused;JNI_OnUnload=mdvm_stub_JNI_OnUnload_unused")
    endif()
    if(TARGET lzma)
        target_sources(lzma PRIVATE
            "${MDVM_ART_ROOT_DIR}/art/multiplatform/windows/lzma_aes_stub.c")
        target_compile_definitions(lzma PRIVATE MY_CPU_X86_OR_AMD64=0)
    endif()
    set_target_properties(art-compiler PROPERTIES
        PREFIX ""
        OUTPUT_NAME "art-compiler"
        WINDOWS_EXPORT_ALL_SYMBOLS OFF)
    target_sources(art-compiler PRIVATE "${_repo}/compat/src/art_compiler_exports.cc")
    target_sources(art PRIVATE "${_repo}/compat/src/art_pe_inline_exports.cc")
    target_include_directories(art-compiler PRIVATE "${MDVM_ART_ROOT_DIR}/art/compiler")
    target_compile_definitions(art-compiler PRIVATE ART_CONSUMING_LIBART)
    target_link_options(art PRIVATE
        "LINKER:/DEF:${_repo}/compat/art_runtime_consumer_exports.def")
    set_property(TARGET art APPEND PROPERTY LINK_DEPENDS
        "${_repo}/compat/art_runtime_consumer_exports.def")
    target_link_options(art-compiler PRIVATE
        "LINKER:/DEF:${_repo}/compat/art_compiler_exports.def")
    set_source_files_properties(
        "${MDVM_NATIVE_SRC_ROOT_DIR}/external/fmtlib/src/format.cc"
        PROPERTIES COMPILE_OPTIONS "-fexceptions;-UNDEBUG")
endif()
