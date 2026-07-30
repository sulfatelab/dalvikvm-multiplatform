# Unified ART target-test registry. Historical Windows phase directories remain
# source/evidence locations during migration; they do not own product graphs.

if(NOT ART_TARGET_OS_OR_RUNTIME STREQUAL "windows")
    return()
endif()
if(NOT ART_TARGET_CPU_ARCH)
    message(FATAL_ERROR "ART tests require ART_TARGET_CPU_ARCH from the target profile")
endif()

option(ART_ENABLE_TARGET_RUNTIME_TESTS
    "Register target executables with CTest when the configured host can run them"
    OFF)

get_filename_component(_art_test_repo_root "${CMAKE_CURRENT_LIST_DIR}/../.." ABSOLUTE)
set(_art_test_verify_root "${_art_test_repo_root}/tools/verify")
set(_art_test_phase1 "${_art_test_verify_root}/windows_x64_phase1")
set(_art_test_phase4 "${_art_test_verify_root}/windows_x64_phase4")
set(_art_test_w013 "${_art_test_verify_root}/windows_x64_w013")
set(_art_test_w025 "${_art_test_verify_root}/windows_x64_w025")

function(art_define_test_stage stage)
    if(NOT stage MATCHES "^w[0-9][0-9][0-9]$")
        message(FATAL_ERROR "Non-canonical ART test stage: ${stage}")
    endif()
    set(group "art-test-stage-${stage}")
    if(TARGET "${group}")
        message(FATAL_ERROR "ART test stage is defined more than once: ${stage}")
    endif()
    add_custom_target("${group}")
    set_property(TARGET "${group}" PROPERTY ART_TEST_STAGE "${stage}")
    set_property(GLOBAL APPEND PROPERTY ART_TEST_STAGES "${stage}")
    add_dependencies(art-tests "${group}")
endfunction()

function(art_add_windows_probe)
    set(options PRODUCT_POLICY RUNNABLE WINDOWS_EXPORT_ALL_SYMBOLS)
    set(one_value_args NAME STAGE TYPE ARCH OUTPUT_NAME PREFIX)
    set(multi_value_args
        SOURCES INCLUDE_DIRS LINK_LIBRARIES COMPILE_OPTIONS COMPILE_DEFINITIONS
        LINK_OPTIONS CONTRACTS)
    cmake_parse_arguments(PROBE "${options}" "${one_value_args}" "${multi_value_args}" ${ARGN})

    foreach(required NAME STAGE TYPE ARCH)
        if(NOT PROBE_${required})
            message(FATAL_ERROR "ART Windows probe is missing ${required}")
        endif()
    endforeach()
    if(NOT TARGET "art-test-stage-${PROBE_STAGE}")
        message(FATAL_ERROR "Unknown ART test stage for ${PROBE_NAME}: ${PROBE_STAGE}")
    endif()
    if(NOT PROBE_ARCH STREQUAL "any" AND
       NOT PROBE_ARCH STREQUAL ART_TARGET_CPU_ARCH)
        return()
    endif()

    if(PROBE_TYPE STREQUAL "EXECUTABLE")
        add_executable("${PROBE_NAME}" EXCLUDE_FROM_ALL ${PROBE_SOURCES})
    elseif(PROBE_TYPE STREQUAL "SHARED")
        add_library("${PROBE_NAME}" SHARED EXCLUDE_FROM_ALL ${PROBE_SOURCES})
    else()
        message(FATAL_ERROR "Unsupported ART Windows probe type: ${PROBE_TYPE}")
    endif()

    if(PROBE_INCLUDE_DIRS)
        target_include_directories("${PROBE_NAME}" PRIVATE ${PROBE_INCLUDE_DIRS})
    endif()
    if(PROBE_LINK_LIBRARIES)
        target_link_libraries("${PROBE_NAME}" PRIVATE ${PROBE_LINK_LIBRARIES})
    endif()
    if(PROBE_COMPILE_OPTIONS)
        target_compile_options("${PROBE_NAME}" PRIVATE ${PROBE_COMPILE_OPTIONS})
    endif()
    if(PROBE_COMPILE_DEFINITIONS)
        target_compile_definitions("${PROBE_NAME}" PRIVATE ${PROBE_COMPILE_DEFINITIONS})
    endif()
    if(PROBE_LINK_OPTIONS)
        target_link_options("${PROBE_NAME}" PRIVATE ${PROBE_LINK_OPTIONS})
    endif()
    target_link_options("${PROBE_NAME}" PRIVATE -fuse-ld=lld)
    if(PROBE_PRODUCT_POLICY)
        target_link_libraries("${PROBE_NAME}" PRIVATE art-test-product-policy)
    endif()
    if(DEFINED PROBE_OUTPUT_NAME)
        set_target_properties("${PROBE_NAME}" PROPERTIES OUTPUT_NAME "${PROBE_OUTPUT_NAME}")
    endif()
    if(DEFINED PROBE_PREFIX)
        set_target_properties("${PROBE_NAME}" PROPERTIES PREFIX "${PROBE_PREFIX}")
    endif()
    if(PROBE_WINDOWS_EXPORT_ALL_SYMBOLS)
        set_target_properties("${PROBE_NAME}" PROPERTIES WINDOWS_EXPORT_ALL_SYMBOLS ON)
    endif()

    set(labels
        "stage:${PROBE_STAGE}"
        "platform:windows"
        "arch:${PROBE_ARCH}")
    foreach(contract IN LISTS PROBE_CONTRACTS)
        list(APPEND labels "contract:${contract}")
    endforeach()
    set_property(TARGET "${PROBE_NAME}" PROPERTY ART_TEST_LABELS "${labels}")
    add_dependencies("art-test-stage-${PROBE_STAGE}" "${PROBE_NAME}")

    if(PROBE_RUNNABLE AND ART_ENABLE_TARGET_RUNTIME_TESTS)
        add_test(NAME "art.${PROBE_STAGE}.${PROBE_NAME}" COMMAND "${PROBE_NAME}")
        set_tests_properties("art.${PROBE_STAGE}.${PROBE_NAME}" PROPERTIES LABELS "${labels}")
    endif()
endfunction()

add_custom_target(art-tests)
foreach(stage w002 w003 w004 w010 w013 w014 w025)
    art_define_test_stage("${stage}")
endforeach()

set(_art_jni_include "${_art_test_repo_root}/vendor/libnativehelper/include_jni")
set(_art_windows_defines
    _CRT_SECURE_NO_WARNINGS NOMINMAX WIN32_LEAN_AND_MEAN NOGDI
    _WIN32_WINNT=0x0A00 NTDDI_VERSION=NTDDI_WIN10_RS4)
set(_art_no_cet "LINKER:/CETCOMPAT:NO")

# Compatibility policy inherited by probes that historically lived in the
# Phase-1 product directory. Standalone OS experiments deliberately omit it.
add_library(art-test-product-policy INTERFACE)
target_include_directories(art-test-product-policy INTERFACE
    "${MDVM_COMPAT_INCLUDE_DIR}"
    "${_art_test_repo_root}/vendor/nativehelper-headers"
    "${MDVM_GENSRC_DIR}/art/aconfig/include"
    "${MDVM_GENSRC_DIR}/art/asm/include")
target_compile_definitions(art-test-product-policy INTERFACE ${_art_windows_defines})
target_compile_options(art-test-product-policy INTERFACE
    "$<$<COMPILE_LANGUAGE:C,CXX>:SHELL:-include ${MDVM_COMPAT_INCLUDE_DIR}/mdvm_windows_x64_prelude.h>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-error>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-unused-command-line-argument>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-deprecated-declarations>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-sign-conversion>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-shorten-64-to-32>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-error=sign-conversion>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-error=shorten-64-to-32>")
target_link_libraries(art-test-product-policy INTERFACE
    windows_x64_posix_stubs ws2_32 synchronization)

# W-002: managed-entry and attach/OSR transitions. The DLL probe is ABI-neutral;
# the unwind inspection executable currently describes PE x86-64 unwind data.
art_add_windows_probe(
    NAME w002attachprobe STAGE w002 TYPE SHARED ARCH any
    SOURCES "${_art_test_phase4}/w002_attach/w002_attach_probe.c"
    INCLUDE_DIRS "${_art_jni_include}"
    LINK_OPTIONS "${_art_no_cet}"
    CONTRACTS jni attach
    PREFIX lib WINDOWS_EXPORT_ALL_SYMBOLS)
art_add_windows_probe(
    NAME win32_osr_unwind_probe STAGE w002 TYPE EXECUTABLE ARCH x86_64
    SOURCES "${_art_test_phase1}/win32_osr_unwind_probe.cc"
    CONTRACTS osr unwind PRODUCT_POLICY)

# W-003: quick-frame and native ABI preservation. Only the XMM sentinel is tied
# to x86-64 assembly; the C probes are retained for future Windows AArch64.
art_add_windows_probe(
    NAME criticalnativeprobe STAGE w003 TYPE SHARED ARCH any
    SOURCES "${_art_test_phase4}/critical_native/critical_native_probe.c"
    INCLUDE_DIRS "${_art_jni_include}"
    LINK_OPTIONS "${_art_no_cet}"
    CONTRACTS jni native-abi
    PREFIX lib WINDOWS_EXPORT_ALL_SYMBOLS)
art_add_windows_probe(
    NAME nativeabiprobe STAGE w003 TYPE SHARED ARCH any
    SOURCES "${_art_test_phase4}/native_abi/native_abi_probe.c"
    INCLUDE_DIRS "${_art_jni_include}"
    LINK_OPTIONS "${_art_no_cet}"
    CONTRACTS jni native-abi
    PREFIX lib WINDOWS_EXPORT_ALL_SYMBOLS)
art_add_windows_probe(
    NAME w003frameprobe STAGE w003 TYPE SHARED ARCH any
    SOURCES "${_art_test_phase4}/w003_frame_probe/w003_frame_probe.c"
    INCLUDE_DIRS "${_art_jni_include}"
    LINK_OPTIONS "${_art_no_cet}"
    CONTRACTS jni stack
    PREFIX lib WINDOWS_EXPORT_ALL_SYMBOLS)
art_add_windows_probe(
    NAME w003xmmsentinel STAGE w003 TYPE SHARED ARCH x86_64
    SOURCES
        "${_art_test_phase4}/w003_xmm_sentinel/w003_xmm_sentinel.c"
        "${_art_test_phase4}/w003_xmm_sentinel/w003_xmm_sentinel_x86_64.S"
    INCLUDE_DIRS "${_art_jni_include}"
    LINK_OPTIONS "${_art_no_cet}"
    CONTRACTS jni native-abi xmm
    PREFIX lib WINDOWS_EXPORT_ALL_SYMBOLS)

# W-004: runtime embedding and forced-interpreter/JVMTI transitions.
art_add_windows_probe(
    NAME win32_art_embedding_probe STAGE w004 TYPE EXECUTABLE ARCH any
    SOURCES "${_art_test_phase1}/win32_art_embedding_probe.cc"
    INCLUDE_DIRS "${_art_jni_include}"
    CONTRACTS embedding runtime-load PRODUCT_POLICY)
art_add_windows_probe(
    NAME jvmtiforceprobe STAGE w004 TYPE SHARED ARCH any
    SOURCES "${_art_test_phase4}/jvmti_force/jvmti_force_probe.c"
    INCLUDE_DIRS
        "${_art_jni_include}"
        "${_art_test_repo_root}/vendor/art/openjdkjvmti/include"
    COMPILE_DEFINITIONS ${_art_windows_defines}
    LINK_OPTIONS "${_art_no_cet}"
    CONTRACTS jvmti interpreter
    OUTPUT_NAME libjvmtiforceprobe WINDOWS_EXPORT_ALL_SYMBOLS)

# W-010: exception dispatch, fault records, sigchain, and debugger interaction.
art_add_windows_probe(
    NAME win32_uef_probe STAGE w010 TYPE EXECUTABLE ARCH any
    SOURCES "${_art_test_phase1}/win32_uef_probe.cc"
    CONTRACTS fault seh PRODUCT_POLICY)
art_add_windows_probe(
    NAME win32_fault_record_probe STAGE w010 TYPE EXECUTABLE ARCH any
    SOURCES "${_art_test_phase1}/win32_fault_record_probe.cc"
    INCLUDE_DIRS "${_art_test_repo_root}/vendor/art"
    CONTRACTS fault seh PRODUCT_POLICY)
art_add_windows_probe(
    NAME win32_sigchain_probe STAGE w010 TYPE EXECUTABLE ARCH x86_64
    SOURCES
        "${_art_test_phase1}/win32_sigchain_probe.cc"
        "${_art_test_phase1}/win32_stack_page_fault_probe.S"
    INCLUDE_DIRS
        "${_art_test_repo_root}/vendor/art"
        "${_art_test_repo_root}/vendor/art/sigchainlib"
        "${MDVM_COMPAT_INCLUDE_DIR}"
    LINK_LIBRARIES sigchain
    CONTRACTS fault sigchain PRODUCT_POLICY)
art_add_windows_probe(
    NAME win32_debugger_probe STAGE w010 TYPE EXECUTABLE ARCH any
    SOURCES "${_art_test_phase1}/win32_debugger_probe.cc"
    CONTRACTS debugger fault PRODUCT_POLICY)

# W-013: ART-owned Windows virtual-memory and allocator contracts.
art_add_windows_probe(
    NAME windows_x64_w013_mem_map_probe STAGE w013 TYPE EXECUTABLE ARCH any
    SOURCES "${_art_test_w013}/W013MemMapPolicyProbe.cc"
    INCLUDE_DIRS "${_art_test_repo_root}/vendor/art/libartbase"
    LINK_LIBRARIES artbase base log
    CONTRACTS virtual-memory PRODUCT_POLICY)
art_add_windows_probe(
    NAME windows_x64_w013_mspace_owner_probe STAGE w013 TYPE EXECUTABLE ARCH any
    SOURCES
        "${_art_test_w013}/W013MspaceOwnerProbe.cc"
        "${_art_test_repo_root}/vendor/art/runtime/gc/allocator/art-dlmalloc.cc"
    INCLUDE_DIRS
        "${_art_test_repo_root}/vendor/art/runtime"
        "${_art_test_repo_root}/vendor/art/libartbase"
        "${MDVM_NATIVE_SRC_ROOT_DIR}/external/dlmalloc"
    LINK_LIBRARIES artbase base log
    CONTRACTS allocator virtual-memory PRODUCT_POLICY)

# W-014: native thread-stack, guard-page, CET, and stack high-water contracts.
art_add_windows_probe(
    NAME windows_x64_pthread_once_probe STAGE w014 TYPE EXECUTABLE ARCH any RUNNABLE
    SOURCES "${_art_test_phase4}/pthread_once_probe.c"
    CONTRACTS threads PRODUCT_POLICY)
art_add_windows_probe(
    NAME win32_thread_stack_probe STAGE w014 TYPE EXECUTABLE ARCH any RUNNABLE
    SOURCES "${_art_test_phase1}/win32_thread_stack_probe.c"
    CONTRACTS stack threads PRODUCT_POLICY)
art_add_windows_probe(
    NAME win32_stack_page_probe STAGE w014 TYPE EXECUTABLE ARCH x86_64
    SOURCES
        "${_art_test_phase1}/win32_stack_page_probe.cc"
        "${_art_test_phase1}/win32_stack_page_fault_probe.S"
        "${_art_test_repo_root}/vendor/art/runtime/multiplatform/windows/stack_windows.cc"
    INCLUDE_DIRS "${_art_test_repo_root}/vendor/art/runtime/multiplatform/windows"
    CONTRACTS stack fault PRODUCT_POLICY)
art_add_windows_probe(
    NAME win32_stack_growth_probe STAGE w014 TYPE EXECUTABLE ARCH x86_64
    SOURCES
        "${_art_test_phase1}/win32_stack_growth_probe.cc"
        "${_art_test_phase1}/win32_stack_page_fault_probe.S"
        "${_art_test_repo_root}/vendor/art/runtime/multiplatform/windows/stack_windows.cc"
    INCLUDE_DIRS "${_art_test_repo_root}/vendor/art/runtime/multiplatform/windows"
    CONTRACTS stack fault PRODUCT_POLICY)
art_add_windows_probe(
    NAME win32_stack_growth_rx_probe STAGE w014 TYPE EXECUTABLE ARCH any
    SOURCES "${_art_test_phase1}/win32_stack_growth_rx_probe.c"
    CONTRACTS stack executable-memory)
art_add_windows_probe(
    NAME win32_stack_pregrow_probe STAGE w014 TYPE EXECUTABLE ARCH x86_64
    SOURCES
        "${_art_test_phase1}/win32_stack_pregrow_probe.c"
        "${_art_test_phase1}/win32_stack_implicit_probe.S"
    LINK_LIBRARIES psapi
    COMPILE_DEFINITIONS ${_art_windows_defines}
    CONTRACTS stack fault)
art_add_windows_probe(
    NAME win32_cet_policy_probe STAGE w014 TYPE EXECUTABLE ARCH any
    SOURCES
        "${_art_test_phase1}/win32_cet_policy_probe.cc"
        "${_art_test_repo_root}/vendor/art/runtime/multiplatform/windows/cet_compat.cc"
    INCLUDE_DIRS "${_art_test_repo_root}/vendor/art/runtime/multiplatform/windows"
    CONTRACTS cet stack PRODUCT_POLICY)
art_add_windows_probe(
    NAME fs1stackhighwater STAGE w014 TYPE SHARED ARCH any
    SOURCES "${_art_test_phase4}/fs1_stack_high_water/fs1_stack_high_water_probe.cc"
    INCLUDE_DIRS "${_art_jni_include}"
    LINK_OPTIONS "${_art_no_cet}"
    CONTRACTS stack jni
    PREFIX lib WINDOWS_EXPORT_ALL_SYMBOLS)

# W-025: JIT section policy and PE unwind registration/lifecycle.
art_add_windows_probe(
    NAME win32_jit_unwind_info_probe STAGE w025 TYPE EXECUTABLE ARCH x86_64
    SOURCES "${_art_test_phase1}/win32_jit_unwind_info_probe.cc"
    INCLUDE_DIRS "${_art_test_repo_root}/vendor/art/compiler"
    CONTRACTS jit unwind PRODUCT_POLICY)
art_add_windows_probe(
    NAME win32_jit_unwind_registry_probe STAGE w025 TYPE EXECUTABLE ARCH x86_64
    SOURCES
        "${_art_test_phase1}/win32_jit_unwind_registry_probe.cc"
        "${_art_test_repo_root}/vendor/art/runtime/multiplatform/windows/jit_unwind_windows.cc"
    INCLUDE_DIRS
        "${_art_test_repo_root}/vendor/art"
        "${_art_test_repo_root}/vendor/art/compiler"
        "${_art_test_repo_root}/vendor/art/libartbase"
    LINK_LIBRARIES artbase base log
    CONTRACTS jit unwind PRODUCT_POLICY)
art_add_windows_probe(
    NAME jitunwindlifecycleprobe STAGE w025 TYPE SHARED ARCH x86_64
    SOURCES "${_art_test_phase1}/win32_jit_unwind_lifecycle_probe.cc"
    LINK_LIBRARIES art
    COMPILE_OPTIONS
        -fno-rtti -Wno-thread-safety -Wno-unused-command-line-argument
        -Wno-microsoft-cast -Wno-invalid-offsetof
    COMPILE_DEFINITIONS ART_CONSUMING_LIBART
    CONTRACTS jit unwind
    PREFIX lib OUTPUT_NAME jitunwindlifecycleprobe WINDOWS_EXPORT_ALL_SYMBOLS PRODUCT_POLICY)
art_add_windows_probe(
    NAME w025jitlifecyclestressprobe STAGE w025 TYPE SHARED ARCH x86_64
    SOURCES "${_art_test_w025}/W025JitLifecycleStressProbe.cc"
    LINK_LIBRARIES art
    COMPILE_OPTIONS
        -fno-rtti -Wno-thread-safety -Wno-unused-command-line-argument
        -Wno-microsoft-cast -Wno-invalid-offsetof
    COMPILE_DEFINITIONS ART_CONSUMING_LIBART
    CONTRACTS jit unwind stress
    PREFIX lib OUTPUT_NAME w025jitlifecyclestressprobe WINDOWS_EXPORT_ALL_SYMBOLS PRODUCT_POLICY)
art_add_windows_probe(
    NAME w025jitmappingprobe STAGE w025 TYPE SHARED ARCH any
    SOURCES "${_art_test_w025}/W025JitMappingProbe.cc"
    INCLUDE_DIRS
        "${_art_test_repo_root}/vendor/art/runtime"
        "${_art_test_repo_root}/vendor/art/libartbase"
    LINK_LIBRARIES art psapi
    COMPILE_OPTIONS
        -fno-rtti -Wno-thread-safety -Wno-unused-command-line-argument
        -Wno-microsoft-cast -Wno-invalid-offsetof
    COMPILE_DEFINITIONS ART_CONSUMING_LIBART
    CONTRACTS jit virtual-memory
    PREFIX lib OUTPUT_NAME w025jitmappingprobe WINDOWS_EXPORT_ALL_SYMBOLS PRODUCT_POLICY)
art_add_windows_probe(
    NAME windows_x64_w025_section_policy_probe STAGE w025 TYPE EXECUTABLE ARCH any
    SOURCES "${_art_test_w025}/W025SectionPolicyProbe.cc"
    LINK_LIBRARIES onecore psapi
    COMPILE_OPTIONS -Xclang -cfguard
    LINK_OPTIONS "LINKER:/guard:cf"
    CONTRACTS jit executable-memory cfg
    OUTPUT_NAME W025SectionPolicyProbe PRODUCT_POLICY)
art_add_windows_probe(
    NAME windows_x64_w025_policy_launcher STAGE w025 TYPE EXECUTABLE ARCH any
    SOURCES "${_art_test_w025}/W025PolicyLauncher.cc"
    CONTRACTS jit process-policy
    OUTPUT_NAME W025PolicyLauncher PRODUCT_POLICY)
