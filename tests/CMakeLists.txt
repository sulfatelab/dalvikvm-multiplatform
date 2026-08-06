# Unified ART target-test registry. Historical Windows phase directories remain
# source/evidence locations during migration; they do not own product graphs.

option(ART_ENABLE_TARGET_RUNTIME_TESTS
    "Register target executables with CTest when the configured host can run them"
    OFF)

get_filename_component(_art_test_repo_root "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
set(_art_test_cases_root "${CMAKE_CURRENT_LIST_DIR}/cases")
set(_art_managed_builder "${CMAKE_CURRENT_LIST_DIR}/support/managed_artifact.py")
set(_art_boot_image_builder
    "${_art_test_repo_root}/tools/build_boot_image.py")
set(_art_windows_aot_identity
    "${_art_test_repo_root}/tools/windows_aot_identity.py")
set(_art_windows_boot_image_runner
    "${_art_test_repo_root}/tools/run_windows_boot_image.py")
set(_art_conscrypt_constants_builder
    "${CMAKE_CURRENT_LIST_DIR}/support/generate_conscrypt_constants.py")
set(_art_managed_root "${CMAKE_CURRENT_BINARY_DIR}/managed")
set(_art_r8_jar "${_art_test_repo_root}/vendor/r8/r8.jar")
set(_art_icu_data
    "${_art_test_repo_root}/vendor/icu/icu4c/source/stubdata/icudt72l.dat")
set(_art_security_properties
    "${_art_test_repo_root}/compat/java-resources/java/security/security.properties")
set(_art_cacerts_dir
    "${_art_test_repo_root}/native/runtime-assets/etc/security/cacerts")
if(NOT ART_JDK_ROOT)
    message(FATAL_ERROR
        "ART_JDK_ROOT is required; configure through tools/build_art.py")
endif()
if(NOT EXISTS "${_art_r8_jar}")
    message(FATAL_ERROR "Pinned D8/R8 tool is missing: ${_art_r8_jar}")
endif()
if(NOT EXISTS "${_art_icu_data}")
    message(FATAL_ERROR "Pinned ICU data is missing: ${_art_icu_data}")
endif()

set(_art_boot_source_roots
    "${_art_test_repo_root}/vendor/libcore/ojluni/src/main/java"
    "${_art_test_repo_root}/vendor/libcore/libart/src/main/java"
    "${_art_test_repo_root}/vendor/libcore/dalvik/src/main/java"
    "${_art_test_repo_root}/vendor/libcore/luni/src/main/java"
    "${_art_test_repo_root}/vendor/libcore/xml/src/main/java"
    "${_art_test_repo_root}/vendor/libcore/json/src/main/java"
    "${_art_test_repo_root}/vendor/icu/android_icu4j/src/main/java"
    "${_art_test_repo_root}/vendor/icu/android_icu4j/libcore_bridge/src/java"
    "${_art_test_repo_root}/vendor/java-external/conscrypt/repackaged/common/src/main/java"
    "${_art_test_repo_root}/vendor/java-external/conscrypt/repackaged/platform/src/main/java"
    "${_art_test_repo_root}/vendor/java-external/conscrypt/publicapi/src/main/java"
    "${_art_test_repo_root}/vendor/java-external/okhttp/repackaged/android/src/main/java"
    "${_art_test_repo_root}/vendor/java-external/okhttp/repackaged/okhttp/src/main/java"
    "${_art_test_repo_root}/vendor/java-external/okhttp/repackaged/okhttp-urlconnection/src/main/java"
    "${_art_test_repo_root}/vendor/java-external/okhttp/repackaged/okhttp-android-support/src/main/java"
    "${_art_test_repo_root}/vendor/java-external/okhttp/repackaged/okio/okio/src/main/java"
    "${_art_test_repo_root}/compat/java-stubs")
set(_art_boot_sources)
foreach(_art_boot_source_root IN LISTS _art_boot_source_roots)
    file(GLOB_RECURSE _art_boot_source_tree CONFIGURE_DEPENDS
        "${_art_boot_source_root}/*.java")
    list(APPEND _art_boot_sources ${_art_boot_source_tree})
endforeach()
set(_art_boot_aconfig
    "${_art_test_repo_root}/vendor/libcore/libcore.aconfig"
    "${_art_test_repo_root}/vendor/art/build/flags/art-flags.aconfig"
    "${_art_test_repo_root}/vendor/art/build/flags/art-rw-flags.aconfig")
set(_art_boot_jar "${_art_managed_root}/boot.jar")
set(_art_boot_manifest "${_art_managed_root}/boot.manifest.json")
set(_art_boot_classes "${_art_managed_root}/classes/boot")
set(_art_conscrypt_constants_source
    "${_art_test_repo_root}/vendor/java-external/conscrypt/constants/src/gen/cpp/generate_constants.cc")
set(_art_boringssl_include
    "${_art_test_repo_root}/vendor/external/boringssl/src/include")
set(_art_conscrypt_constants_java
    "${_art_managed_root}/generated-inputs/conscrypt/com/android/org/conscrypt/NativeConstants.java")
file(GLOB_RECURSE _art_boringssl_headers CONFIGURE_DEPENDS
    "${_art_boringssl_include}/*.h")

# Native Windows does not inherit a Visual Studio developer environment. Build
# this host helper with the same plain-Clang GNU driver contract as the product,
# but select libraries for the build host architecture rather than the target
# architecture. Linux hosts need no additional host SDK arguments.
set(_art_conscrypt_host_driver_options)
if(CMAKE_HOST_WIN32)
    set(ART_HOST_WINDOWS_BUNDLE_ROOT "" CACHE PATH
        "Regular-file Windows host SDK/runtime bundle for build-time tools")
    if(ART_HOST_WINDOWS_BUNDLE_ROOT)
        set(_art_conscrypt_host_bundle "${ART_HOST_WINDOWS_BUNDLE_ROOT}")
    elseif(ART_TARGET_PLATFORM STREQUAL "windows")
        set(_art_conscrypt_host_bundle "${ART_TARGET_BUNDLE_ROOT}")
    else()
        message(FATAL_ERROR
            "Windows-hosted non-Windows targets require "
            "ART_HOST_WINDOWS_BUNDLE_ROOT for Conscrypt host codegen")
    endif()

    string(TOLOWER "${CMAKE_HOST_SYSTEM_PROCESSOR}" _art_conscrypt_host_processor)
    if(_art_conscrypt_host_processor MATCHES "^(amd64|x86_64)$")
        set(_art_conscrypt_host_arch x86_64)
        set(_art_conscrypt_host_triple x86_64-pc-windows-msvc)
    elseif(_art_conscrypt_host_processor MATCHES "^(arm64|aarch64)$")
        set(_art_conscrypt_host_arch aarch64)
        set(_art_conscrypt_host_triple aarch64-pc-windows-msvc)
    else()
        message(FATAL_ERROR
            "Unsupported Windows host processor for Conscrypt codegen: "
            "${CMAKE_HOST_SYSTEM_PROCESSOR}")
    endif()

    execute_process(
        COMMAND "${CMAKE_CXX_COMPILER}" -print-resource-dir
        OUTPUT_VARIABLE _art_conscrypt_clang_resource
        OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE _art_conscrypt_resource_rc)
    if(NOT _art_conscrypt_resource_rc EQUAL 0)
        message(FATAL_ERROR "Cannot query host Clang resource directory")
    endif()
    file(TO_CMAKE_PATH
        "${_art_conscrypt_clang_resource}" _art_conscrypt_clang_resource)

    list(APPEND _art_conscrypt_host_driver_options
        "--compile-option=--target=${_art_conscrypt_host_triple}"
        "--compile-option=-nostdinc++"
        "--compile-option=-nostartfiles"
        "--compile-option=-nostdlib"
        "--compile-option=-stdlib=libc++"
        "--compile-option=-D_DLL"
        "--compile-option=-D_MT"
        "--compile-option=-Xclang"
        "--compile-option=--dependent-lib=msvcrt")
    set(_art_conscrypt_host_includes
        "${_art_conscrypt_host_bundle}/lib/libcxx/include/c++/v1"
        "${_art_conscrypt_clang_resource}/include"
        "${_art_conscrypt_host_bundle}/xwin/sdk/include/ucrt"
        "${_art_conscrypt_host_bundle}/xwin/sdk/include/shared"
        "${_art_conscrypt_host_bundle}/xwin/sdk/include/um"
        "${_art_conscrypt_host_bundle}/xwin/crt/include")
    foreach(_art_conscrypt_host_include IN LISTS _art_conscrypt_host_includes)
        if(NOT IS_DIRECTORY "${_art_conscrypt_host_include}")
            message(FATAL_ERROR
                "Windows host bundle is missing an include directory: "
                "${_art_conscrypt_host_include}")
        endif()
        list(APPEND _art_conscrypt_host_driver_options
            "--compile-option=-isystem"
            "--compile-option=${_art_conscrypt_host_include}")
    endforeach()

    list(APPEND _art_conscrypt_host_driver_options
        "--link-option=-fuse-ld=lld"
        "--link-option=-fuse-ld=lld-link"
        "--link-option=-Xlinker"
        "--link-option=/subsystem:console")
    set(_art_conscrypt_host_lib_dirs
        "${_art_conscrypt_host_bundle}/lib/libcxx/lib"
        "${_art_conscrypt_host_bundle}/xwin/crt/lib/${_art_conscrypt_host_arch}"
        "${_art_conscrypt_host_bundle}/xwin/sdk/lib/ucrt/${_art_conscrypt_host_arch}"
        "${_art_conscrypt_host_bundle}/xwin/sdk/lib/um/${_art_conscrypt_host_arch}")
    file(GLOB _art_conscrypt_compiler_rt_dirs LIST_DIRECTORIES true
        "${_art_conscrypt_host_bundle}/lib/clang/*/lib/windows")
    list(APPEND _art_conscrypt_host_lib_dirs ${_art_conscrypt_compiler_rt_dirs})
    foreach(_art_conscrypt_host_lib_dir IN LISTS _art_conscrypt_host_lib_dirs)
        if(NOT IS_DIRECTORY "${_art_conscrypt_host_lib_dir}")
            message(FATAL_ERROR
                "Windows host bundle is missing a library directory: "
                "${_art_conscrypt_host_lib_dir}")
        endif()
        list(APPEND _art_conscrypt_host_driver_options
            "--link-option=-L${_art_conscrypt_host_lib_dir}")
    endforeach()
    set(_art_conscrypt_host_libraries
        "${_art_conscrypt_host_bundle}/lib/libcxx/lib/c++.lib"
        "${_art_conscrypt_host_bundle}/xwin/crt/lib/${_art_conscrypt_host_arch}/msvcprt.lib"
        "${_art_conscrypt_host_bundle}/xwin/crt/lib/${_art_conscrypt_host_arch}/msvcrt.lib"
        "${_art_conscrypt_host_bundle}/xwin/crt/lib/${_art_conscrypt_host_arch}/vcruntime.lib"
        "${_art_conscrypt_host_bundle}/xwin/sdk/lib/ucrt/${_art_conscrypt_host_arch}/ucrt.lib"
        "${_art_conscrypt_host_bundle}/xwin/sdk/lib/um/${_art_conscrypt_host_arch}/kernel32.lib")
    foreach(_art_conscrypt_host_library IN LISTS _art_conscrypt_host_libraries)
        if(NOT EXISTS "${_art_conscrypt_host_library}")
            message(FATAL_ERROR
                "Windows host bundle is missing a runtime library: "
                "${_art_conscrypt_host_library}")
        endif()
        list(APPEND _art_conscrypt_host_driver_options
            "--link-option=${_art_conscrypt_host_library}")
    endforeach()
endif()
add_custom_command(
    OUTPUT "${_art_conscrypt_constants_java}"
    BYPRODUCTS
        "${_art_managed_root}/host-tools/conscrypt/compile.stdout.txt"
        "${_art_managed_root}/host-tools/conscrypt/compile.stderr.txt"
        "${_art_managed_root}/host-tools/conscrypt/generator.stderr.txt"
    COMMAND "${Python3_EXECUTABLE}" "${_art_conscrypt_constants_builder}"
        --compiler "${CMAKE_CXX_COMPILER}"
        --source "${_art_conscrypt_constants_source}"
        --include-dir "${_art_boringssl_include}"
        --work-root "${_art_managed_root}/host-tools/conscrypt"
        --output "${_art_conscrypt_constants_java}"
        --package com.android.org.conscrypt
        ${_art_conscrypt_host_driver_options}
    DEPENDS
        "${_art_conscrypt_constants_builder}"
        "${_art_conscrypt_constants_source}"
        ${_art_boringssl_headers}
    COMMENT "Generating Conscrypt NativeConstants.java with host plain Clang"
    VERBATIM)
add_custom_command(
    OUTPUT "${_art_boot_jar}" "${_art_boot_manifest}"
    BYPRODUCTS
        "${_art_managed_root}/inputs/boot.classes.jar"
        "${_art_managed_root}/arguments/boot.sources.args"
        "${_art_managed_root}/logs/boot.javac.log"
        "${_art_managed_root}/logs/boot.d8.log"
    COMMAND "${Python3_EXECUTABLE}" "${_art_managed_builder}"
        --jdk-root "${ART_JDK_ROOT}"
        --r8-jar "${_art_r8_jar}"
        --source-root "${_art_test_repo_root}"
        --output-root "${_art_managed_root}"
        --name boot
        --source-tree "${_art_test_repo_root}/vendor/libcore/ojluni/src/main/java"
        --source-tree "${_art_test_repo_root}/vendor/libcore/libart/src/main/java"
        --source-tree "${_art_test_repo_root}/vendor/libcore/dalvik/src/main/java"
        --source-tree "${_art_test_repo_root}/vendor/libcore/luni/src/main/java"
        --source-tree "${_art_test_repo_root}/vendor/libcore/xml/src/main/java"
        --source-tree "${_art_test_repo_root}/vendor/libcore/json/src/main/java"
        --source-tree "${_art_test_repo_root}/vendor/icu/android_icu4j/src/main/java"
        --source-tree "${_art_test_repo_root}/vendor/icu/android_icu4j/libcore_bridge/src/java"
        --source-tree "${_art_test_repo_root}/vendor/java-external/conscrypt/repackaged/common/src/main/java"
        --source-tree "${_art_test_repo_root}/vendor/java-external/conscrypt/repackaged/platform/src/main/java"
        --source-tree "${_art_test_repo_root}/vendor/java-external/conscrypt/publicapi/src/main/java"
        --source-tree "${_art_test_repo_root}/vendor/java-external/okhttp/repackaged/android/src/main/java"
        --source-tree "${_art_test_repo_root}/vendor/java-external/okhttp/repackaged/okhttp/src/main/java"
        --source-tree "${_art_test_repo_root}/vendor/java-external/okhttp/repackaged/okhttp-urlconnection/src/main/java"
        --source-tree "${_art_test_repo_root}/vendor/java-external/okhttp/repackaged/okhttp-android-support/src/main/java"
        --source-tree "${_art_test_repo_root}/vendor/java-external/okhttp/repackaged/okio/okio/src/main/java"
        --source-tree "${_art_test_repo_root}/compat/java-stubs"
        --source "${_art_conscrypt_constants_java}"
        --resource
            "${_art_security_properties}"
            java/security/security.properties
        --exclude vendor/libcore/luni/src/main/java/libcore/net/http/Dns.java
        --exclude vendor/libcore/luni/src/main/java/libcore/net/http/HttpURLConnectionFactory.java
        --exclude vendor/libcore/libart/src/main/java/java/lang/AndroidHardcodedSystemProperties.java
        --aconfig "${_art_test_repo_root}/vendor/libcore/libcore.aconfig"
        --aconfig "${_art_test_repo_root}/vendor/art/build/flags/art-flags.aconfig"
        --aconfig "${_art_test_repo_root}/vendor/art/build/flags/art-rw-flags.aconfig"
        --patch-module "${_art_test_repo_root}/vendor/libcore/ojluni/src/main/java"
        --javac-option=-g:none
        --javac-option=-encoding
        --javac-option=UTF-8
        --javac-option=-XDstringConcat=inline
        --javac-option=-nowarn
        --javac-option=-proc:none
        --android-platform-build
    DEPENDS
        "${_art_managed_builder}"
        "${_art_r8_jar}"
        "${_art_conscrypt_constants_java}"
        "${_art_security_properties}"
        ${_art_boot_sources}
        ${_art_boot_aconfig}
    COMMENT "Building target-neutral ART boot.jar with configured JDK 21 and D8"
    VERBATIM)
add_custom_target(art-managed-boot-jar
    DEPENDS "${_art_boot_jar}" "${_art_boot_manifest}")
add_custom_target(art-runtime-package-inputs ALL)
add_dependencies(art-runtime-package-inputs art-managed-boot-jar)

set(ART_BOOT_IMAGE_PARALLEL "16" CACHE STRING
    "Bounded dex2oat worker count for a natively generated boot image")
if(NOT ART_BOOT_IMAGE_PARALLEL MATCHES "^[1-9][0-9]*$")
    message(FATAL_ERROR
        "ART_BOOT_IMAGE_PARALLEL must be a positive integer")
endif()
set(_art_boot_image_root "${CMAKE_BINARY_DIR}/runtime/boot-image")
set(_art_boot_image_dir
    "${_art_boot_image_root}/${ART_TARGET_AOSP_ARCH}")
list(FIND ART_TARGET_CAPABILITIES "boot_image" _art_boot_image_capability)
set(_art_experimental_windows_boot_image FALSE)
if(ART_TARGET_ID STREQUAL "windows-x86_64-msvc")
    set(_art_experimental_windows_boot_image TRUE)
endif()
if(_art_boot_image_capability GREATER -1 OR _art_experimental_windows_boot_image)
    if(ART_ENABLE_TARGET_RUNTIME_TESTS)
        if(NOT TARGET dex2oat)
            message(FATAL_ERROR
                "Target ${ART_TARGET_ID} enables boot-image generation without dex2oat")
        endif()
        set(_art_boot_image_library_args
            --library-dir "$<TARGET_FILE_DIR:dex2oat>")
        if(_art_experimental_windows_boot_image)
            list(APPEND _art_boot_image_library_args
                --library-dir "${ART_TARGET_BUNDLE_ROOT}/lib/libcxx/bin")
        endif()
        add_custom_command(
            OUTPUT
                "${_art_boot_image_dir}/boot.art"
                "${_art_boot_image_dir}/boot.oat"
                "${_art_boot_image_dir}/boot.vdex"
                "${_art_boot_image_root}/manifest.json"
            BYPRODUCTS "${_art_boot_image_root}/dex2oat.log"
            COMMAND "${Python3_EXECUTABLE}" "${_art_boot_image_builder}"
                --target-id "${ART_TARGET_ID}"
                --dex2oat "$<TARGET_FILE:dex2oat>"
                --boot-jar "${_art_boot_jar}"
                --output-root "${_art_boot_image_root}"
                --instruction-set "${ART_TARGET_AOSP_ARCH}"
                --parallel "${ART_BOOT_IMAGE_PARALLEL}"
                ${_art_boot_image_library_args}
            DEPENDS
                dex2oat
                art-managed-boot-jar
                "${_art_boot_image_builder}"
                "${_art_windows_aot_identity}"
                "${_art_boot_jar}"
            COMMENT "Building relocatable ${ART_TARGET_ID} ART boot image"
            VERBATIM)
        add_custom_target(art-runtime-boot-image
            DEPENDS
                "${_art_boot_image_dir}/boot.art"
                "${_art_boot_image_dir}/boot.oat"
                "${_art_boot_image_dir}/boot.vdex"
                "${_art_boot_image_root}/manifest.json")
        if(_art_boot_image_capability GREATER -1)
            add_dependencies(art-runtime-package-inputs art-runtime-boot-image)
        endif()
    else()
        # Cross hosts cannot execute target dex2oat. Keep the target name valid
        # for catalog ownership without pretending that an image was built.
        add_custom_target(art-runtime-boot-image)
    endif()
endif()

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

function(_art_test_json_array output)
    set(result "[")
    set(separator "")
    foreach(value IN LISTS ARGN)
        string(APPEND result "${separator}\"${value}\"")
        set(separator ",")
    endforeach()
    string(APPEND result "]")
    set(${output} "${result}" PARENT_SCOPE)
endfunction()

function(art_add_target_probe)
    set(options PRODUCT_POLICY WINDOWS_EXPORT_ALL_SYMBOLS)
    set(one_value_args NAME STAGE TYPE OUTPUT_NAME PREFIX EXECUTION TIMEOUT)
    set(multi_value_args
        SOURCES INCLUDE_DIRS LINK_LIBRARIES COMPILE_OPTIONS COMPILE_DEFINITIONS
        LINK_OPTIONS CONTRACTS DEPENDS PLATFORMS TARGET_ARCHES TARGET_ABIS
        TARGET_IDS CAPABILITIES COMMAND)
    cmake_parse_arguments(PROBE "${options}" "${one_value_args}" "${multi_value_args}" ${ARGN})

    foreach(required NAME STAGE TYPE EXECUTION)
        if(NOT PROBE_${required})
            message(FATAL_ERROR "ART target probe is missing ${required}")
        endif()
    endforeach()
    if(NOT TARGET "art-test-stage-${PROBE_STAGE}")
        message(FATAL_ERROR "Unknown ART test stage for ${PROBE_NAME}: ${PROBE_STAGE}")
    endif()
    if(NOT PROBE_EXECUTION MATCHES "^(compile-only|target-runnable|host-review|cross-runner)$")
        message(FATAL_ERROR
            "Unsupported execution mode for ${PROBE_NAME}: ${PROBE_EXECUTION}")
    endif()
    if(PROBE_TIMEOUT AND NOT PROBE_TIMEOUT MATCHES "^[1-9][0-9]*$")
        message(FATAL_ERROR
            "ART target probe ${PROBE_NAME} has invalid timeout: ${PROBE_TIMEOUT}")
    endif()
    if(PROBE_TIMEOUT AND NOT PROBE_EXECUTION STREQUAL "target-runnable")
        message(FATAL_ERROR
            "Only target-runnable probe ${PROBE_NAME} may declare a timeout")
    endif()
    if(PROBE_TARGET_IDS AND
       (PROBE_PLATFORMS OR PROBE_TARGET_ARCHES OR PROBE_TARGET_ABIS))
        message(FATAL_ERROR
            "${PROBE_NAME} must use TARGET_IDS or broad identity selectors, not both")
    endif()
    if(NOT PROBE_TARGET_IDS AND
       (NOT PROBE_PLATFORMS OR NOT PROBE_TARGET_ARCHES OR NOT PROBE_TARGET_ABIS))
        message(FATAL_ERROR
            "${PROBE_NAME} requires PLATFORMS, TARGET_ARCHES, and TARGET_ABIS")
    endif()

    foreach(value IN LISTS PROBE_TARGET_IDS)
        list(FIND ART_TARGET_ID_ENUM "${value}" index)
        if(index EQUAL -1)
            message(FATAL_ERROR "${PROBE_NAME} has unknown target ID selector: ${value}")
        endif()
    endforeach()
    foreach(value IN LISTS PROBE_PLATFORMS)
        list(FIND ART_TARGET_PLATFORM_ENUM "${value}" index)
        if(index EQUAL -1)
            message(FATAL_ERROR "${PROBE_NAME} has unknown platform selector: ${value}")
        endif()
    endforeach()
    foreach(value IN LISTS PROBE_TARGET_ARCHES)
        list(FIND ART_TARGET_ARCH_ENUM "${value}" index)
        if(index EQUAL -1)
            message(FATAL_ERROR "${PROBE_NAME} has unknown architecture selector: ${value}")
        endif()
    endforeach()
    foreach(value IN LISTS PROBE_TARGET_ABIS)
        list(FIND ART_TARGET_ABI_ENUM "${value}" index)
        if(index EQUAL -1)
            message(FATAL_ERROR "${PROBE_NAME} has unknown ABI selector: ${value}")
        endif()
    endforeach()

    set(applicable TRUE)
    set(reason "")
    if(PROBE_TARGET_IDS)
        list(FIND PROBE_TARGET_IDS "${ART_TARGET_ID}" index)
        if(index EQUAL -1)
            set(applicable FALSE)
            set(reason "target-id")
        endif()
    else()
        foreach(axis PLATFORM ARCH ABI)
            if(axis STREQUAL "PLATFORM")
                set(current "${ART_TARGET_PLATFORM}")
                set(selectors ${PROBE_PLATFORMS})
                set(axis_name "platform")
            elseif(axis STREQUAL "ARCH")
                set(current "${ART_TARGET_ARCH}")
                set(selectors ${PROBE_TARGET_ARCHES})
                set(axis_name "target-architecture")
            else()
                set(current "${ART_TARGET_ABI}")
                set(selectors ${PROBE_TARGET_ABIS})
                set(axis_name "target-abi")
            endif()
            list(FIND selectors "${current}" index)
            if(applicable AND index EQUAL -1)
                set(applicable FALSE)
                set(reason "${axis_name}")
            endif()
        endforeach()
    endif()
    foreach(capability IN LISTS PROBE_CAPABILITIES)
        list(FIND ART_TARGET_CAPABILITIES "${capability}" index)
        if(applicable AND index EQUAL -1)
            set(applicable FALSE)
            set(reason "capability:${capability}")
        endif()
    endforeach()

    _art_test_json_array(platforms_json ${PROBE_PLATFORMS})
    _art_test_json_array(arches_json ${PROBE_TARGET_ARCHES})
    _art_test_json_array(abis_json ${PROBE_TARGET_ABIS})
    _art_test_json_array(ids_json ${PROBE_TARGET_IDS})
    _art_test_json_array(capabilities_json ${PROBE_CAPABILITIES})
    if(PROBE_TIMEOUT)
        set(timeout_json "${PROBE_TIMEOUT}")
    else()
        set(timeout_json null)
    endif()
    if(applicable)
        set(applicable_json true)
        set(build_status pending)
        if(PROBE_EXECUTION STREQUAL "compile-only")
            set(runtime_status not-required)
        else()
            set(runtime_status pending)
        endif()
    else()
        set(applicable_json false)
        set(build_status not-applicable)
        set(runtime_status not-applicable)
    endif()
    if(applicable AND
       (PROBE_EXECUTION STREQUAL "host-review" OR
        (PROBE_EXECUTION STREQUAL "target-runnable" AND
         ART_ENABLE_TARGET_RUNTIME_TESTS)))
        set(ctest_registered_json true)
    else()
        set(ctest_registered_json false)
    endif()
    set(record
        "    {\"name\":\"${PROBE_NAME}\",\"stage\":\"${PROBE_STAGE}\","
        "\"type\":\"${PROBE_TYPE}\",\"execution\":\"${PROBE_EXECUTION}\","
        "\"applicable\":${applicable_json},\"reason\":\"${reason}\","
        "\"ctest_registered\":${ctest_registered_json},"
        "\"timeout_seconds\":${timeout_json},"
        "\"build_verified\":false,\"runtime_verified\":false,"
        "\"build_status\":\"${build_status}\","
        "\"runtime_status\":\"${runtime_status}\","
        "\"platforms\":${platforms_json},\"target_arches\":${arches_json},"
        "\"target_abis\":${abis_json},\"target_ids\":${ids_json},"
        "\"capabilities\":${capabilities_json}}")
    string(JOIN "" record ${record})
    set_property(GLOBAL APPEND PROPERTY ART_TEST_CATALOG_RECORDS "${record}")

    if(NOT applicable)
        return()
    endif()
    if(PROBE_TYPE STREQUAL "GATE")
        if(NOT PROBE_COMMAND)
            message(FATAL_ERROR "Command gate ${PROBE_NAME} has no COMMAND")
        endif()
        if(PROBE_EXECUTION STREQUAL "compile-only")
            message(FATAL_ERROR
                "Command gate ${PROBE_NAME} cannot be compile-only; use a "
                "host-review, target-runnable, or cross-runner command")
        endif()
        if(PROBE_SOURCES OR PROBE_INCLUDE_DIRS OR PROBE_LINK_LIBRARIES OR
           PROBE_COMPILE_OPTIONS OR PROBE_COMPILE_DEFINITIONS OR
           PROBE_LINK_OPTIONS OR PROBE_PRODUCT_POLICY OR
           PROBE_WINDOWS_EXPORT_ALL_SYMBOLS OR PROBE_OUTPUT_NAME OR PROBE_PREFIX)
            message(FATAL_ERROR
                "Command gate ${PROBE_NAME} cannot declare compile or link inputs")
        endif()
        add_custom_target("${PROBE_NAME}")
    elseif(PROBE_TYPE STREQUAL "MANAGED")
        if(NOT PROBE_SOURCES)
            message(FATAL_ERROR "Managed probe ${PROBE_NAME} has no Java sources")
        endif()
        if(PROBE_INCLUDE_DIRS OR PROBE_LINK_LIBRARIES OR PROBE_COMPILE_OPTIONS OR
           PROBE_COMPILE_DEFINITIONS OR PROBE_LINK_OPTIONS OR PROBE_PRODUCT_POLICY OR
           PROBE_WINDOWS_EXPORT_ALL_SYMBOLS OR PROBE_PREFIX)
            message(FATAL_ERROR
                "Managed probe ${PROBE_NAME} cannot declare native compile/link inputs")
        endif()
        if(PROBE_EXECUTION STREQUAL "target-runnable" AND NOT PROBE_COMMAND)
            message(FATAL_ERROR
                "Runnable managed probe ${PROBE_NAME} requires a shell-free COMMAND")
        endif()
        if(PROBE_OUTPUT_NAME)
            set(_art_managed_name "${PROBE_OUTPUT_NAME}")
        else()
            set(_art_managed_name "${PROBE_NAME}")
        endif()
        set(_art_managed_sources)
        foreach(_art_managed_source IN LISTS PROBE_SOURCES)
            list(APPEND _art_managed_sources --source "${_art_managed_source}")
        endforeach()
        set(_art_managed_jar "${_art_managed_root}/${_art_managed_name}.jar")
        set(_art_managed_manifest
            "${_art_managed_root}/${_art_managed_name}.manifest.json")
        add_custom_command(
            OUTPUT "${_art_managed_jar}" "${_art_managed_manifest}"
            BYPRODUCTS
                "${_art_managed_root}/inputs/${_art_managed_name}.classes.jar"
                "${_art_managed_root}/arguments/${_art_managed_name}.sources.args"
                "${_art_managed_root}/logs/${_art_managed_name}.javac.log"
                "${_art_managed_root}/logs/${_art_managed_name}.d8.log"
            COMMAND "${Python3_EXECUTABLE}" "${_art_managed_builder}"
                --jdk-root "${ART_JDK_ROOT}"
                --r8-jar "${_art_r8_jar}"
                --source-root "${_art_test_repo_root}"
                --output-root "${_art_managed_root}"
                --name "${_art_managed_name}"
                --boot-classpath "${_art_boot_classes}"
                ${_art_managed_sources}
            DEPENDS
                art-managed-boot-jar
                "${_art_managed_builder}"
                "${_art_r8_jar}"
                ${PROBE_SOURCES}
            COMMENT "Building managed ART probe ${PROBE_NAME}"
            COMMAND_EXPAND_LISTS
            VERBATIM)
        add_custom_target("${PROBE_NAME}"
            DEPENDS "${_art_managed_jar}" "${_art_managed_manifest}")
        add_dependencies("${PROBE_NAME}" art-managed-boot-jar)
        add_dependencies(art-managed-tests "${PROBE_NAME}")
        set_property(TARGET "${PROBE_NAME}" PROPERTY ART_MANAGED_JAR
            "${_art_managed_jar}")
    else()
        if(NOT TARGET art-test-target-policy)
            message(FATAL_ERROR
                "${PROBE_NAME} is applicable but no target test policy is defined")
        endif()
        if(PROBE_TYPE STREQUAL "EXECUTABLE")
            add_executable("${PROBE_NAME}" EXCLUDE_FROM_ALL ${PROBE_SOURCES})
        elseif(PROBE_TYPE STREQUAL "SHARED")
            if(NOT PROBE_EXECUTION STREQUAL "compile-only")
                message(FATAL_ERROR
                    "Shared probe ${PROBE_NAME} must be a compile-only support "
                    "artifact; declare its behavioral owner as MANAGED or GATE")
            endif()
            add_library("${PROBE_NAME}" SHARED EXCLUDE_FROM_ALL ${PROBE_SOURCES})
        else()
            message(FATAL_ERROR "Unsupported ART target probe type: ${PROBE_TYPE}")
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
        target_link_libraries("${PROBE_NAME}" PRIVATE art-test-target-policy)
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
    endif()

    set(labels
        "stage:${PROBE_STAGE}"
        "platform:${ART_TARGET_PLATFORM}"
        "arch:${ART_TARGET_ARCH}"
        "abi:${ART_TARGET_ABI}"
        "execution:${PROBE_EXECUTION}")
    foreach(contract IN LISTS PROBE_CONTRACTS)
        list(APPEND labels "contract:${contract}")
    endforeach()
    set_property(TARGET "${PROBE_NAME}" PROPERTY ART_TEST_LABELS "${labels}")
    if(PROBE_DEPENDS)
        add_dependencies("${PROBE_NAME}" ${PROBE_DEPENDS})
    endif()
    add_dependencies("art-test-stage-${PROBE_STAGE}" "${PROBE_NAME}")

    if(PROBE_EXECUTION STREQUAL "host-review" OR
       (PROBE_EXECUTION STREQUAL "target-runnable" AND
        ART_ENABLE_TARGET_RUNTIME_TESTS))
        if(PROBE_EXECUTION STREQUAL "host-review")
            if(NOT PROBE_TYPE STREQUAL "GATE")
                message(FATAL_ERROR
                    "Host-review probe ${PROBE_NAME} must be a command gate")
            endif()
            add_test(NAME "art.${PROBE_STAGE}.${PROBE_NAME}"
                COMMAND ${PROBE_COMMAND})
        elseif(PROBE_TYPE STREQUAL "GATE" OR PROBE_TYPE STREQUAL "MANAGED")
            add_test(NAME "art.${PROBE_STAGE}.${PROBE_NAME}"
                COMMAND ${PROBE_COMMAND})
        elseif(PROBE_COMMAND)
            add_test(NAME "art.${PROBE_STAGE}.${PROBE_NAME}"
                COMMAND ${PROBE_COMMAND})
        else()
            # Keep target runtime files explicit and outside the host environment:
            # generated ART DLLs live in CMAKE_BINARY_DIR and the pinned libc++ DLL
            # lives in the regular-file target bundle.
            add_test(NAME "art.${PROBE_STAGE}.${PROBE_NAME}"
                COMMAND "${CMAKE_COMMAND}" -E env
                    "PATH=${CMAKE_BINARY_DIR};${_art_bundle_lib}/libcxx/bin;$ENV{PATH}"
                    "$<TARGET_FILE:${PROBE_NAME}>")
        endif()
        set_tests_properties("art.${PROBE_STAGE}.${PROBE_NAME}" PROPERTIES
            LABELS "${labels}"
            WORKING_DIRECTORY "${CMAKE_BINARY_DIR}")
        if(PROBE_TIMEOUT)
            set_tests_properties("art.${PROBE_STAGE}.${PROBE_NAME}" PROPERTIES
                TIMEOUT "${PROBE_TIMEOUT}")
        endif()
    endif()
endfunction()

add_custom_target(art-tests)
add_custom_target(art-managed-tests)
foreach(stage w002 w003 w004 w010 w013 w014 w025 w027 w028 w029 w030)
    art_define_test_stage("${stage}")
endforeach()

set(_art_jni_include "${_art_test_repo_root}/vendor/libnativehelper/include_jni")

add_library(art-test-target-policy INTERFACE)
target_link_options(art-test-target-policy INTERFACE -fuse-ld=lld)
if(ART_TARGET_PLATFORM STREQUAL "windows")
    set(_art_windows_defines
        _CRT_SECURE_NO_WARNINGS NOMINMAX WIN32_LEAN_AND_MEAN NOGDI
        _WIN32_WINNT=0x0A00 NTDDI_VERSION=NTDDI_WIN10_RS4)
    set(_art_no_cet "LINKER:/CETCOMPAT:NO")
    set(_art_windows_image_options
        "LINKER:/DYNAMICBASE"
        "LINKER:/NXCOMPAT"
        "LINKER:/HIGHENTROPYVA")

# Every probe compiles with the exact target SDK, libc++, runtime, and linker
# policy used by the product graph. Tests are declared after the product-wide
# target loop in the parent directory, so make this inheritance explicit
# instead of relying on directory-global flags or host tool discovery.
target_include_directories(art-test-target-policy INTERFACE
    "${_art_windows_cxx_include}"
    ${_art_windows_system_includes})
target_compile_options(art-test-target-policy INTERFACE
    "$<$<COMPILE_LANGUAGE:CXX>:-nostdinc++>"
    "$<$<COMPILE_LANGUAGE:CXX>:SHELL:-isystem ${_art_windows_cxx_include}>"
    ${_art_windows_system_compile_options}
    "$<$<COMPILE_LANGUAGE:CXX>:-stdlib=libc++>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-fms-compatibility>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-fms-extensions>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-fno-omit-frame-pointer>")
foreach(_art_test_bundle_lib_dir
        "${ART_TARGET_BUNDLE_ROOT}/lib/libcxx/lib"
        "${ART_TARGET_BUNDLE_ROOT}/xwin/sdk/lib/ucrt/${ART_TARGET_AOSP_ARCH}"
        "${ART_TARGET_BUNDLE_ROOT}/xwin/sdk/lib/um/${ART_TARGET_AOSP_ARCH}"
        "${ART_TARGET_BUNDLE_ROOT}/xwin/crt/lib/${ART_TARGET_AOSP_ARCH}")
    if(EXISTS "${_art_test_bundle_lib_dir}")
        target_link_directories(art-test-target-policy INTERFACE
            "${_art_test_bundle_lib_dir}")
    endif()
endforeach()
target_link_options(art-test-target-policy INTERFACE
    "${_art_no_cet}" ${_art_windows_image_options})
target_link_libraries(art-test-target-policy INTERFACE
    art_windows_cxx windows_x64_posix_stubs ws2_32 synchronization)

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
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-error>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-unused-command-line-argument>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-deprecated-declarations>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-sign-conversion>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-shorten-64-to-32>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-error=sign-conversion>"
    "$<$<COMPILE_LANGUAGE:C,CXX>:-Wno-error=shorten-64-to-32>")
endif()

# Every probe states its current exact applicability. The broad Windows
# selector is intentionally limited to the only verified architecture/ABI; it
# can be expanded one exact value at a time after native validation.
include("${CMAKE_CURRENT_LIST_DIR}/cmake/ArtTestApplicability.cmake")
foreach(_art_test_llvm_tool ART_LLVM_READOBJ ART_LLVM_OBJDUMP)
    if(NOT ${_art_test_llvm_tool})
        message(FATAL_ERROR
            "${_art_test_llvm_tool} is required for shell-free object reviewers")
    endif()
endforeach()
if(ART_TARGET_PLATFORM STREQUAL "windows" AND NOT ART_LLVM_PDBUTIL)
    message(FATAL_ERROR
        "ART_LLVM_PDBUTIL is required for shell-free Windows PDB reviewers")
endif()
set(_art_managed_runtime_library_args
    --library-dir "$<TARGET_FILE_DIR:dalvikvm>")
if(ART_TARGET_PLATFORM STREQUAL "windows")
    list(APPEND _art_managed_runtime_library_args
        --library-dir "${ART_TARGET_BUNDLE_ROOT}/lib/libcxx/bin")
endif()
set(_art_target_runner_args)
if(ART_TARGET_RUNNER OR ART_TARGET_RUNNER_ROOT)
    if(NOT ART_TARGET_RUNNER OR NOT ART_TARGET_RUNNER_ROOT)
        message(FATAL_ERROR
            "ART_TARGET_RUNNER and ART_TARGET_RUNNER_ROOT must be set together")
    endif()
    list(APPEND _art_target_runner_args
        --runner "${ART_TARGET_RUNNER}"
        --runner-arg=-L
        "--runner-arg=${ART_TARGET_RUNNER_ROOT}")
endif()

# W-002: managed-entry and attach/OSR transitions.
art_add_target_probe(
    NAME w002attachprobe STAGE w002 TYPE SHARED EXECUTION compile-only
    ${_art_windows_current_selector}
    SOURCES "${_art_test_cases_root}/attached-thread-entry/probe.c"
    INCLUDE_DIRS "${_art_jni_include}"
    LINK_OPTIONS "${_art_no_cet}"
    CONTRACTS jni attach
    PREFIX lib WINDOWS_EXPORT_ALL_SYMBOLS)
art_add_target_probe(
    NAME win32_osr_unwind_probe STAGE w002 TYPE EXECUTABLE EXECUTION target-runnable
    ${_art_windows_x86_64_msvc_selector}
    SOURCES "${_art_test_cases_root}/osr-unwind/probe.cc"
    LINK_LIBRARIES dbghelp
    DEPENDS art
    CONTRACTS osr unwind PRODUCT_POLICY)
art_add_target_probe(
    NAME windows_w002_managed_entry_structure STAGE w002 TYPE GATE
    EXECUTION host-review
    ${_art_windows_x86_64_msvc_selector}
    DEPENDS art
    CONTRACTS jni osr unwind source-policy
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/windows/check_w002_managed_entries.py"
        --build "${CMAKE_BINARY_DIR}"
        --llvm-readobj
            "${ART_LLVM_READOBJ}"
        --llvm-objdump
            "${ART_LLVM_OBJDUMP}")
art_add_target_probe(
    NAME managed_w002_attach STAGE w002 TYPE MANAGED EXECUTION target-runnable
    TIMEOUT 600
    ${_art_windows_current_selector}
    SOURCES "${_art_test_cases_root}/attached-thread-entry/W002AttachProbe.java"
    DEPENDS w002attachprobe dalvikvm icu_jni javacore openjdk
    CONTRACTS jni attach
    OUTPUT_NAME w002attachprobe
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/windows/w002_managed_entry_gate.py"
        --case attach
        --target-id "${ART_TARGET_ID}"
        --dalvikvm "$<TARGET_FILE:dalvikvm>"
        --boot-jar "${_art_boot_jar}"
        --app-jar "${_art_managed_root}/w002attachprobe.jar"
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/w002-attach"
        --icu-data "${_art_icu_data}"
        --jni-dir "$<TARGET_FILE_DIR:w002attachprobe>"
        --library-dir "$<TARGET_FILE_DIR:w002attachprobe>"
        ${_art_managed_runtime_library_args}
        --repeat 2
        --timeout 120)
art_add_target_probe(
    NAME managed_w002_osr STAGE w002 TYPE MANAGED EXECUTION target-runnable
    TIMEOUT 600
    ${_art_windows_x86_64_msvc_selector}
    SOURCES "${_art_test_cases_root}/osr-unwind/W002OsrProbe.java"
    DEPENDS dalvikvm icu_jni javacore openjdk
    CONTRACTS osr unwind
    OUTPUT_NAME w002osrprobe
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/windows/w002_managed_entry_gate.py"
        --case osr
        --target-id "${ART_TARGET_ID}"
        --dalvikvm "$<TARGET_FILE:dalvikvm>"
        --boot-jar "${_art_boot_jar}"
        --app-jar "${_art_managed_root}/w002osrprobe.jar"
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/w002-osr"
        --icu-data "${_art_icu_data}"
        ${_art_managed_runtime_library_args}
        --repeat 2
        --timeout 120)

# W-003: quick-frame and native ABI preservation. CriticalNative and
# normal/FastNative include their separately accepted Linux AArch64 target;
# no other target is inferred from sharing their source.
art_add_target_probe(
    NAME criticalnativeprobe STAGE w003 TYPE SHARED EXECUTION compile-only
    ${_art_critical_native_ids_selector}
    SOURCES "${_art_test_cases_root}/jni-critical-native/probe.c"
    INCLUDE_DIRS "${_art_jni_include}"
    LINK_OPTIONS "${_art_no_cet}"
    CONTRACTS jni native-abi
    PREFIX lib WINDOWS_EXPORT_ALL_SYMBOLS)
art_add_target_probe(
    NAME nativeabiprobe STAGE w003 TYPE SHARED EXECUTION compile-only
    ${_art_native_abi_ids_selector}
    SOURCES "${_art_test_cases_root}/jni-native-abi/probe.c"
    INCLUDE_DIRS "${_art_jni_include}"
    LINK_OPTIONS "${_art_no_cet}"
    CONTRACTS jni native-abi
    PREFIX lib WINDOWS_EXPORT_ALL_SYMBOLS)
art_add_target_probe(
    NAME w003frameprobe STAGE w003 TYPE SHARED EXECUTION compile-only
    ${_art_windows_current_selector}
    SOURCES "${_art_test_cases_root}/w003-frame-probe/probe.c"
    INCLUDE_DIRS "${_art_jni_include}"
    LINK_OPTIONS "${_art_no_cet}"
    CONTRACTS jni stack
    PREFIX lib WINDOWS_EXPORT_ALL_SYMBOLS)
art_add_target_probe(
    NAME w003xmmsentinel STAGE w003 TYPE SHARED EXECUTION compile-only
    ${_art_windows_x86_64_msvc_selector}
    SOURCES
        "${_art_test_cases_root}/w003-xmm-sentinel/probe.c"
        "${_art_test_cases_root}/w003-xmm-sentinel/sentinel_x86_64.S"
    INCLUDE_DIRS "${_art_jni_include}"
    LINK_OPTIONS "${_art_no_cet}"
    CONTRACTS jni native-abi xmm
    PREFIX lib WINDOWS_EXPORT_ALL_SYMBOLS)
art_add_target_probe(
    NAME windows_w003_quick_boundary_structure STAGE w003 TYPE GATE
    EXECUTION host-review
    ${_art_windows_x86_64_msvc_selector}
    DEPENDS art w003xmmsentinel
    CONTRACTS stack native-abi xmm codegen source-policy
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/windows/check_w003_quick_boundaries.py"
        --build "${CMAKE_BINARY_DIR}"
        --variant "${ART_TEST_VARIANT}"
        --llvm-readobj
            "${ART_LLVM_READOBJ}"
        --llvm-objdump
            "${ART_LLVM_OBJDUMP}")
art_add_target_probe(
    NAME managed_critical_native STAGE w003 TYPE MANAGED EXECUTION target-runnable
    TIMEOUT 1200
    ${_art_critical_native_ids_selector}
    SOURCES
        "${_art_test_cases_root}/jni-critical-native/CriticalNativeProbe.java"
        "${_art_test_cases_root}/jni-critical-native/CriticalNativeDlsymProbe.java"
    DEPENDS criticalnativeprobe dalvikvm icu_jni javacore openjdk
    CONTRACTS jni native-abi
    OUTPUT_NAME criticalnativeprobe
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/w003_managed_gate.py"
        --case critical-native
        --target-id "${ART_TARGET_ID}"
        --dalvikvm "$<TARGET_FILE:dalvikvm>"
        --boot-jar "${_art_boot_jar}"
        --app-jar "${_art_managed_root}/criticalnativeprobe.jar"
        --probe "$<TARGET_FILE:criticalnativeprobe>"
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/w003-critical-native"
        --icu-data "${_art_icu_data}"
        ${_art_managed_runtime_library_args}
        ${_art_target_runner_args}
        --repeat 2
        --timeout 180)
art_add_target_probe(
    NAME managed_native_abi STAGE w003 TYPE MANAGED EXECUTION target-runnable
    TIMEOUT 900
    ${_art_native_abi_ids_selector}
    SOURCES "${_art_test_cases_root}/jni-native-abi/FastNativeAbiProbe.java"
    DEPENDS nativeabiprobe dalvikvm icu_jni javacore openjdk
    CONTRACTS jni native-abi
    OUTPUT_NAME fastnativeabiprobe
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/w003_managed_gate.py"
        --case native-abi
        --target-id "${ART_TARGET_ID}"
        --dalvikvm "$<TARGET_FILE:dalvikvm>"
        --boot-jar "${_art_boot_jar}"
        --app-jar "${_art_managed_root}/fastnativeabiprobe.jar"
        --probe "$<TARGET_FILE:nativeabiprobe>"
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/w003-native-abi"
        --icu-data "${_art_icu_data}"
        ${_art_managed_runtime_library_args}
        ${_art_target_runner_args}
        --repeat 2
        --timeout 180)
art_add_target_probe(
    NAME managed_w003_xmm_sentinel STAGE w003 TYPE MANAGED EXECUTION target-runnable
    TIMEOUT 1200
    ${_art_windows_x86_64_msvc_selector}
    SOURCES "${_art_test_cases_root}/w003-xmm-sentinel/W003XmmSentinelProbe.java"
    DEPENDS w003xmmsentinel dalvikvm icu_jni javacore openjdk
    CONTRACTS jni native-abi xmm
    OUTPUT_NAME w003xmmsentinelprobe
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/w003_managed_gate.py"
        --case xmm
        --target-id "${ART_TARGET_ID}"
        --dalvikvm "$<TARGET_FILE:dalvikvm>"
        --boot-jar "${_art_boot_jar}"
        --app-jar "${_art_managed_root}/w003xmmsentinelprobe.jar"
        --probe "$<TARGET_FILE:w003xmmsentinel>"
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/w003-xmm"
        --icu-data "${_art_icu_data}"
        ${_art_managed_runtime_library_args}
        --repeat 2
        --timeout 180)
if(ART_TEST_VARIANT STREQUAL "win32-frame-attribution")
    art_add_target_probe(
        NAME managed_w003_frame STAGE w003 TYPE MANAGED EXECUTION target-runnable
        TIMEOUT 1800
        ${_art_windows_current_selector}
        SOURCES "${_art_test_cases_root}/w003-frame-probe/W003FrameProbe.java"
        DEPENDS w003frameprobe dalvikvm icu_jni javacore openjdk
        CONTRACTS jni stack
        OUTPUT_NAME w003frameprobe
        COMMAND
            "${Python3_EXECUTABLE}"
            "${_art_test_repo_root}/tests/support/w003_managed_gate.py"
            --case frame
            --target-id "${ART_TARGET_ID}"
            --dalvikvm "$<TARGET_FILE:dalvikvm>"
            --boot-jar "${_art_boot_jar}"
            --app-jar "${_art_managed_root}/w003frameprobe.jar"
            --probe "$<TARGET_FILE:w003frameprobe>"
            --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/w003-frame"
            --icu-data "${_art_icu_data}"
            ${_art_managed_runtime_library_args}
            --repeat 2
            --timeout 240)
else()
    art_add_target_probe(
        NAME managed_w003_frame STAGE w003 TYPE MANAGED EXECUTION compile-only
        ${_art_windows_current_selector}
        SOURCES "${_art_test_cases_root}/w003-frame-probe/W003FrameProbe.java"
        DEPENDS w003frameprobe
        CONTRACTS jni stack
        OUTPUT_NAME w003frameprobe)
endif()

# W-004: runtime embedding and forced-interpreter/JVMTI transitions.
art_add_target_probe(
    NAME win32_art_embedding_probe STAGE w004 TYPE EXECUTABLE
    EXECUTION target-runnable TIMEOUT 600
    ${_art_windows_x86_64_msvc_selector}
    SOURCES "${_art_test_cases_root}/art-embedding/probe.cc"
    INCLUDE_DIRS "${_art_jni_include}"
    DEPENDS art-managed-boot-jar art icu_jni javacore openjdk openjdkjvm
    CONTRACTS embedding runtime-load PRODUCT_POLICY
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_cases_root}/art-embedding/run.py"
        --target-id "${ART_TARGET_ID}"
        --probe "$<TARGET_FILE:win32_art_embedding_probe>"
        --boot-jar "${_art_boot_jar}"
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/art-embedding"
        --icu-data "${_art_icu_data}"
        ${_art_managed_runtime_library_args}
        --repeat 2
        --timeout 240)
art_add_target_probe(
    NAME jvmtiforceprobe STAGE w004 TYPE SHARED EXECUTION compile-only
    ${_art_windows_current_selector}
    SOURCES "${_art_test_cases_root}/jvmti-force/probe.c"
    INCLUDE_DIRS
        "${_art_jni_include}"
        "${_art_test_repo_root}/vendor/art/openjdkjvmti/include"
    COMPILE_DEFINITIONS ${_art_windows_defines}
    LINK_OPTIONS "${_art_no_cet}"
    CONTRACTS jvmti interpreter
    OUTPUT_NAME libjvmtiforceprobe WINDOWS_EXPORT_ALL_SYMBOLS)
art_add_target_probe(
    NAME managed_jvmti_force STAGE w004 TYPE MANAGED EXECUTION target-runnable
    TIMEOUT 1200
    ${_art_windows_current_selector}
    SOURCES "${_art_test_cases_root}/jvmti-force/JvmtiForceProbe.java"
    DEPENDS jvmtiforceprobe dalvikvm icu_jni javacore openjdk openjdkjvmti
    CONTRACTS jvmti interpreter
    OUTPUT_NAME jvmtiforceprobe
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_cases_root}/jvmti-force/run.py"
        --target-id "${ART_TARGET_ID}"
        --dalvikvm "$<TARGET_FILE:dalvikvm>"
        --boot-jar "${_art_boot_jar}"
        --app-jar "${_art_managed_root}/jvmtiforceprobe.jar"
        --agent "$<TARGET_FILE:jvmtiforceprobe>"
        --plugin "$<TARGET_FILE:openjdkjvmti>"
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/jvmti-force"
        --icu-data "${_art_icu_data}"
        ${_art_managed_runtime_library_args}
        --repeat 3
        --timeout 180)
art_add_target_probe(
    NAME windows_w004_runtime_load_structure STAGE w004 TYPE GATE
    EXECUTION host-review
    ${_art_windows_x86_64_msvc_selector}
    DEPENDS art openjdkjvmti
    CONTRACTS runtime-load jvmti codegen source-policy
    COMMAND
        "${CMAKE_COMMAND}" -E env
        "LLVM_READOBJ=${ART_LLVM_READOBJ}"
        "LLVM_OBJDUMP=${ART_LLVM_OBJDUMP}"
        "NINJA=${CMAKE_MAKE_PROGRAM}"
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/windows/check_w004_runtime_load.py"
        --build "${CMAKE_BINARY_DIR}")
art_add_target_probe(
    NAME managed_imageless_hello STAGE w004 TYPE MANAGED EXECUTION target-runnable
    ${_art_imageless_runtime_ids_selector}
    SOURCES "${_art_test_cases_root}/imageless-runtime/Hello.java"
    DEPENDS dalvikvm icu_jni javacore openjdk
    CONTRACTS runtime-load imageless smoke
    OUTPUT_NAME hello
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/runtime_gate.py"
        managed
        --target-id "${ART_TARGET_ID}"
        --dalvikvm "$<TARGET_FILE:dalvikvm>"
        --boot-jar "${_art_boot_jar}"
        --app-jar "${_art_managed_root}/hello.jar"
        --main-class Hello
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/imageless-hello"
        --icu-data "${_art_icu_data}"
        ${_art_managed_runtime_library_args}
        ${_art_target_runner_args}
        --vm-option=-Xint
        --expect "Hello from dalvikvm!"
        --expect "main end exception=0"
        --forbid AssertionError)
art_add_target_probe(
    NAME managed_boot_image_hello STAGE w004 TYPE GATE
    EXECUTION target-runnable TIMEOUT 180
    ${_art_linux_x86_64_gnu_selector}
    CAPABILITIES boot_image
    DEPENDS
        art-runtime-boot-image
        managed_imageless_hello
        dalvikvm
        icu_jni
        javacore
        openjdk
    CONTRACTS runtime-load boot-image oat packaging
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/runtime_gate.py"
        managed
        --target-id "${ART_TARGET_ID}"
        --dalvikvm "$<TARGET_FILE:dalvikvm>"
        --boot-jar "${_art_boot_jar}"
        --boot-image-dir "${_art_boot_image_root}"
        --app-jar "${_art_managed_root}/hello.jar"
        --main-class Hello
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/boot-image-hello"
        --icu-data "${_art_icu_data}"
        ${_art_managed_runtime_library_args}
        ${_art_target_runner_args}
        --expect "Hello from dalvikvm!"
        --expect "main end exception=0"
        --forbid AssertionError)
art_add_target_probe(
    NAME managed_gc_stress STAGE w004 TYPE MANAGED EXECUTION target-runnable
    ${_art_gc_stress_ids_selector}
    SOURCES "${_art_test_cases_root}/imageless-runtime/GcStressProbe.java"
    DEPENDS dalvikvm icu_jni javacore openjdk
    CONTRACTS runtime-load gc stress
    OUTPUT_NAME gcstressprobe
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/runtime_gate.py"
        managed
        --target-id "${ART_TARGET_ID}"
        --dalvikvm "$<TARGET_FILE:dalvikvm>"
        --boot-jar "${_art_boot_jar}"
        --app-jar "${_art_managed_root}/gcstressprobe.jar"
        --main-class GcStressProbe
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/gc-stress"
        --icu-data "${_art_icu_data}"
        ${_art_managed_runtime_library_args}
        ${_art_target_runner_args}
        --vm-option=-Xint
        --expect "gcstress.ok=true"
        --expect "GcStressProbe.done=ok"
        --expect "main end exception=0"
        --forbid AssertionError)
set(_art_runtime_stress_expected_HandleLeakProbe
    "files.ok=true n=400"
    "socks.ok=true n=80"
    "final=handle-final"
    "handleleak.ok=true"
    "HandleLeakProbe.done=ok")
set(_art_runtime_stress_expected_PerfSmokeProbe
    "perf.ok=true"
    "PerfSmokeProbe.done=ok")
set(_art_runtime_stress_expected_ThreadHeavyProbe
    "threads=24 iters=3000 counter=72000"
    "interrupt.ok=true"
    "threadheavy.ok=true"
    "ThreadHeavyProbe.done=ok")
foreach(_art_runtime_stress_class HandleLeakProbe PerfSmokeProbe ThreadHeavyProbe)
    string(TOLOWER "${_art_runtime_stress_class}" _art_runtime_stress_name)
    if(_art_runtime_stress_class STREQUAL "HandleLeakProbe")
        set(_art_runtime_stress_selector ${_art_handle_leak_ids_selector})
    elseif(_art_runtime_stress_class STREQUAL "PerfSmokeProbe")
        set(_art_runtime_stress_selector ${_art_perf_smoke_ids_selector})
    elseif(_art_runtime_stress_class STREQUAL "ThreadHeavyProbe")
        set(_art_runtime_stress_selector ${_art_thread_heavy_ids_selector})
    else()
        message(FATAL_ERROR
            "missing exact selector for ${_art_runtime_stress_class}")
    endif()
    set(_art_runtime_stress_marker_arguments)
    foreach(_art_runtime_stress_marker IN LISTS
            _art_runtime_stress_expected_${_art_runtime_stress_class})
        list(APPEND _art_runtime_stress_marker_arguments
            --expect "${_art_runtime_stress_marker}")
    endforeach()
    art_add_target_probe(
        NAME "managed_${_art_runtime_stress_name}" STAGE w004
        TYPE MANAGED EXECUTION target-runnable
        ${_art_runtime_stress_selector}
        SOURCES
            "${_art_test_cases_root}/managed-runtime-stress/${_art_runtime_stress_class}.java"
        TIMEOUT 600
        DEPENDS dalvikvm icu_jni javacore openjdk
        CONTRACTS runtime-load stress
        OUTPUT_NAME "${_art_runtime_stress_name}"
        COMMAND
            "${Python3_EXECUTABLE}"
            "${_art_test_repo_root}/tests/support/runtime_gate.py"
            managed
            --target-id "${ART_TARGET_ID}"
            --dalvikvm "$<TARGET_FILE:dalvikvm>"
            --boot-jar "${_art_boot_jar}"
            --app-jar "${_art_managed_root}/${_art_runtime_stress_name}.jar"
            --main-class "${_art_runtime_stress_class}"
            --work-root
                "${CMAKE_CURRENT_BINARY_DIR}/results/${_art_runtime_stress_name}"
            --icu-data "${_art_icu_data}"
            ${_art_managed_runtime_library_args}
            ${_art_target_runner_args}
            --vm-option=-Xint
            ${_art_runtime_stress_marker_arguments}
            --expect "main end exception=0"
            --forbid AssertionError
            --timeout 180)
endforeach()
art_add_target_probe(
    NAME managed_math_critical STAGE w004 TYPE MANAGED EXECUTION target-runnable
    ${_art_math_critical_ids_selector}
    SOURCES "${_art_test_cases_root}/math-critical/MathCriticalProbe.java"
    DEPENDS dalvikvm icu_jni javacore openjdk
    CONTRACTS math critical-native
    OUTPUT_NAME mathcriticalprobe
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_cases_root}/math-critical/run.py"
        --target-id "${ART_TARGET_ID}"
        --dalvikvm "$<TARGET_FILE:dalvikvm>"
        --boot-jar "${_art_boot_jar}"
        --app-jar "${_art_managed_root}/mathcriticalprobe.jar"
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/math-critical"
        --icu-data "${_art_icu_data}"
        ${_art_managed_runtime_library_args}
        ${_art_target_runner_args}
        --repeat 2
        --timeout 180)

# These managed libcore probes default to the current Windows selector until
# each behavioral contract is reviewed and assigned its own exact target set.
set(_art_libcore_managed_classes
    PathProbe AbsPathProbe AsyncCloseProbe BnProbe CoreProbe DnsProbe ExecProbe
    GcForced GcProbe GoldenApp InterruptProbe IoProbe Ipv6Probe LocaleProbe
    NetProbe OsConstantsProbe OsErrnoProbe PropsProbe RtMem
    SocketAddressProbe SslProviderProbe ThreadStressProbe ThrowProbe UdpProbe
    XmlProbe ZipProbe)
set(_art_libcore_runnable_classes
    PathProbe AbsPathProbe AsyncCloseProbe BnProbe CoreProbe DnsProbe GcForced
    GcProbe GoldenApp InterruptProbe IoProbe ExecProbe Ipv6Probe LocaleProbe
    NetProbe OsErrnoProbe OsConstantsProbe PropsProbe RtMem SocketAddressProbe
    SslProviderProbe ThreadStressProbe ThrowProbe UdpProbe XmlProbe ZipProbe)
foreach(_art_libcore_class IN LISTS _art_libcore_managed_classes)
    string(TOLOWER "${_art_libcore_class}" _art_libcore_name)
    list(FIND _art_libcore_runnable_classes
        "${_art_libcore_class}" _art_libcore_runnable_index)
    if(_art_libcore_runnable_index EQUAL -1)
        set(_art_libcore_execution compile-only)
        set(_art_libcore_runtime_arguments)
    else()
        set(_art_libcore_execution target-runnable)
        set(_art_libcore_additional_dependencies)
        set(_art_libcore_additional_command_arguments)
        if(_art_libcore_class STREQUAL "PathProbe")
            list(APPEND _art_libcore_additional_dependencies
                managed_imageless_hello)
            list(APPEND _art_libcore_additional_command_arguments
                --hello-jar "${_art_managed_root}/hello.jar")
        elseif(_art_libcore_class STREQUAL "AbsPathProbe")
            list(APPEND _art_libcore_additional_dependencies
                managed_imageless_hello managed_pathprobe)
            list(APPEND _art_libcore_additional_command_arguments
                --hello-jar "${_art_managed_root}/hello.jar"
                --path-jar "${_art_managed_root}/pathprobe.jar")
        elseif(_art_libcore_class STREQUAL "SslProviderProbe")
            list(APPEND _art_libcore_additional_dependencies javacrypto)
            list(APPEND _art_libcore_additional_command_arguments
                --cacerts-dir "${_art_cacerts_dir}"
                --security-properties "${_art_security_properties}")
        endif()
        set(_art_libcore_runtime_arguments
            TIMEOUT 600
            DEPENDS dalvikvm icu_jni javacore openjdk
                ${_art_libcore_additional_dependencies}
            COMMAND
                "${Python3_EXECUTABLE}"
                "${_art_test_cases_root}/windows-libcore-smoke/run.py"
                --case "${_art_libcore_class}"
                --target-id "${ART_TARGET_ID}"
                --dalvikvm "$<TARGET_FILE:dalvikvm>"
                --boot-jar "${_art_boot_jar}"
                --app-jar "${_art_managed_root}/${_art_libcore_name}.jar"
                --work-root
                    "${CMAKE_CURRENT_BINARY_DIR}/results/libcore-${_art_libcore_name}"
                --icu-data "${_art_icu_data}"
                ${_art_managed_runtime_library_args})
        list(APPEND _art_libcore_runtime_arguments
            ${_art_libcore_additional_command_arguments}
            ${_art_target_runner_args})
    endif()
    if(_art_libcore_class STREQUAL "CoreProbe")
        set(_art_libcore_selector ${_art_core_probe_ids_selector})
    elseif(_art_libcore_class STREQUAL "InterruptProbe")
        set(_art_libcore_selector ${_art_interrupt_probe_ids_selector})
    elseif(_art_libcore_class STREQUAL "RtMem")
        set(_art_libcore_selector ${_art_runtime_memory_ids_selector})
    else()
        set(_art_libcore_selector ${_art_windows_current_selector})
    endif()
    art_add_target_probe(
        NAME "managed_${_art_libcore_name}" STAGE w004
        TYPE MANAGED EXECUTION "${_art_libcore_execution}"
        ${_art_libcore_selector}
        SOURCES
            "${_art_test_cases_root}/windows-libcore-smoke/${_art_libcore_class}.java"
        CONTRACTS libcore runtime-load
        OUTPUT_NAME "${_art_libcore_name}"
        ${_art_libcore_runtime_arguments})
endforeach()
art_add_target_probe(
    NAME windows_crypto_sha_probe STAGE w004 TYPE EXECUTABLE
    EXECUTION target-runnable ${_art_windows_current_selector}
    SOURCES "${_art_test_cases_root}/windows-libcore-smoke/crypto_sha_smoke.c"
    LINK_LIBRARIES crypto_static
    LINK_OPTIONS "${_art_no_cet}"
    CONTRACTS crypto libcore)
art_add_target_probe(
    NAME windows_socket_fd_registry_probe STAGE w013 TYPE EXECUTABLE
    EXECUTION target-runnable ${_art_windows_current_selector}
    SOURCES
        "${_art_test_cases_root}/windows-libcore-smoke/socket_fd_registry_smoke.c"
    LINK_LIBRARIES openjdkjvm ws2_32
    LINK_OPTIONS "${_art_no_cet}"
    CONTRACTS libcore socket fd PRODUCT_POLICY)
art_add_target_probe(
    NAME art_runtime_show_version STAGE w004 TYPE GATE
    EXECUTION target-runnable ${_art_linux_runtime_smoke_ids_selector}
    DEPENDS dalvikvm
    CONTRACTS runtime-load smoke
    COMMAND
        "${CMAKE_COMMAND}" -E env
        "LD_LIBRARY_PATH=${CMAKE_BINARY_DIR}:$ENV{LD_LIBRARY_PATH}"
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/runtime_gate.py"
        show-version
        --dalvikvm "$<TARGET_FILE:dalvikvm>"
        ${_art_target_runner_args}
        --expect "ART version 2.1.0 ${ART_TARGET_AOSP_ARCH}")
art_add_target_probe(
    NAME art_compiler_dso_topology STAGE w004 TYPE EXECUTABLE
    EXECUTION target-runnable
    ${_art_linux_runtime_smoke_ids_selector}
    SOURCES "${_art_test_cases_root}/art-compiler-dso-topology/probe.c"
    LINK_LIBRARIES dl
    COMPILE_OPTIONS -fPIC -fPIE
    LINK_OPTIONS -pie
    DEPENDS art art-compiler
    CONTRACTS runtime-load dso-topology compiler
    COMMAND
        "${CMAKE_COMMAND}" -E env
        "LD_LIBRARY_PATH=${CMAKE_BINARY_DIR}"
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/runtime_gate.py"
        dso-topology
        --target-id "${ART_TARGET_ID}"
        --loader-probe "$<TARGET_FILE:art_compiler_dso_topology>"
        --runtime "$<TARGET_FILE:art>"
        --compiler "$<TARGET_FILE:art-compiler>"
        --compiler-needed libart.so
        --runtime-forbidden libart-compiler.so
        --work-root
            "${CMAKE_CURRENT_BINARY_DIR}/results/art-compiler-dso-topology"
        ${_art_target_runner_args}
        --timeout 60)

# W-010: exception dispatch, fault records, sigchain, and debugger interaction.
art_add_target_probe(
    NAME win32_uef_probe STAGE w010 TYPE EXECUTABLE EXECUTION target-runnable
    TIMEOUT 600
    ${_art_windows_current_selector}
    SOURCES "${_art_test_cases_root}/unhandled-exception-filter/probe.cc"
    CONTRACTS fault seh PRODUCT_POLICY
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_cases_root}/unhandled-exception-filter/run.py"
        --target-id "${ART_TARGET_ID}"
        --probe "$<TARGET_FILE:win32_uef_probe>"
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/w010-uef")
art_add_target_probe(
    NAME win32_fault_record_probe STAGE w010 TYPE EXECUTABLE
    EXECUTION target-runnable TIMEOUT 60
    ${_art_windows_current_selector}
    SOURCES "${_art_test_cases_root}/fault-record/probe.cc"
    INCLUDE_DIRS "${_art_test_repo_root}/vendor/art"
    CONTRACTS fault seh PRODUCT_POLICY)
art_add_target_probe(
    NAME win32_sigchain_probe STAGE w010 TYPE EXECUTABLE
    EXECUTION target-runnable TIMEOUT 60
    ${_art_windows_x86_64_msvc_selector}
    SOURCES
        "${_art_test_cases_root}/sigchain-fault/probe.cc"
        "${_art_test_cases_root}/stack-page-growth/fault_x86_64.S"
    INCLUDE_DIRS
        "${_art_test_repo_root}/vendor/art"
        "${_art_test_repo_root}/vendor/art/sigchainlib"
        "${MDVM_COMPAT_INCLUDE_DIR}"
    LINK_LIBRARIES sigchain
    CONTRACTS fault sigchain PRODUCT_POLICY)
art_add_target_probe(
    NAME win32_debugger_probe STAGE w010 TYPE EXECUTABLE
    EXECUTION target-runnable TIMEOUT 600
    ${_art_windows_current_selector}
    SOURCES "${_art_test_cases_root}/debugger-fault/probe.cc"
    DEPENDS dalvikvm icu_jni javacore openjdk openjdkjvm
    CONTRACTS debugger fault PRODUCT_POLICY
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_cases_root}/debugger-fault/run.py"
        --target-id "${ART_TARGET_ID}"
        --probe "$<TARGET_FILE:win32_debugger_probe>"
        --dalvikvm "$<TARGET_FILE:dalvikvm>"
        --boot-jar "${_art_boot_jar}"
        --app-jar "${_art_managed_root}/w010managedfaultprobe.jar"
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/w010-debugger"
        --icu-data "${_art_icu_data}"
        ${_art_managed_runtime_library_args})
foreach(_art_fatal_class CrashAbortProbe CrashNativeProbe)
    string(TOLOWER "${_art_fatal_class}" _art_fatal_name)
    if(_art_fatal_class STREQUAL "CrashAbortProbe")
        set(_art_fatal_mode abort)
        set(_art_fatal_timeout 300)
    else()
        set(_art_fatal_mode native)
        set(_art_fatal_timeout 900)
    endif()
    art_add_target_probe(
        NAME "managed_${_art_fatal_name}" STAGE w010
        TYPE MANAGED EXECUTION target-runnable TIMEOUT ${_art_fatal_timeout}
        ${_art_windows_current_selector}
        SOURCES "${_art_test_cases_root}/fatal-runtime/${_art_fatal_class}.java"
        DEPENDS dalvikvm icu_jni javacore openjdk openjdkjvm
        CONTRACTS fault fatal-unwind
        OUTPUT_NAME "${_art_fatal_name}"
        COMMAND
            "${Python3_EXECUTABLE}"
            "${_art_test_cases_root}/fatal-runtime/run.py"
            --mode "${_art_fatal_mode}"
            --target-id "${ART_TARGET_ID}"
            --dalvikvm "$<TARGET_FILE:dalvikvm>"
            --boot-jar "${_art_boot_jar}"
            --app-jar "${_art_managed_root}/${_art_fatal_name}.jar"
            --work-root
                "${CMAKE_CURRENT_BINARY_DIR}/results/w010-${_art_fatal_mode}"
            --icu-data "${_art_icu_data}"
            ${_art_managed_runtime_library_args})
endforeach()
art_add_target_probe(
    NAME windows_w010_boundary_unwind_structure STAGE w010 TYPE GATE
    EXECUTION host-review
    ${_art_windows_x86_64_msvc_selector}
    DEPENDS art
    CONTRACTS unwind codegen source-policy
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/windows/check_win32_boundary_unwind.py"
        --art-dll "$<TARGET_FILE:art>"
        --art-pdb
            "$<TARGET_FILE_DIR:art>/$<TARGET_FILE_BASE_NAME:art>.pdb"
        --llvm-readobj "${ART_LLVM_READOBJ}"
        --llvm-pdbutil "${ART_LLVM_PDBUTIL}")
art_add_target_probe(
    NAME managed_w010_fault_recovery STAGE w010 TYPE MANAGED
    EXECUTION target-runnable TIMEOUT 1200
    ${_art_windows_current_selector}
    SOURCES
        "${_art_test_cases_root}/managed-fault-recovery/W010ManagedFaultProbe.java"
    DEPENDS dalvikvm icu_jni javacore openjdk openjdkjvm
    CONTRACTS fault managed-recovery
    OUTPUT_NAME w010managedfaultprobe
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_cases_root}/managed-fault-recovery/run.py"
        --target-id "${ART_TARGET_ID}"
        --dalvikvm "$<TARGET_FILE:dalvikvm>"
        --boot-jar "${_art_boot_jar}"
        --app-jar "${_art_managed_root}/w010managedfaultprobe.jar"
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/w010-managed-fault"
        --icu-data "${_art_icu_data}"
        ${_art_managed_runtime_library_args})
if(TARGET win32_debugger_probe AND TARGET managed_w010_fault_recovery)
    add_dependencies(win32_debugger_probe managed_w010_fault_recovery)
endif()

# W-013: ART-owned Windows virtual-memory and allocator contracts.
art_add_target_probe(
    NAME windows_w013_mem_map_probe STAGE w013 TYPE EXECUTABLE
    EXECUTION target-runnable TIMEOUT 60
    ${_art_windows_current_selector}
    SOURCES "${_art_test_cases_root}/mem-map-policy/probe.cc"
    INCLUDE_DIRS "${_art_test_repo_root}/vendor/art/libartbase"
    LINK_LIBRARIES artbase base log
    CONTRACTS virtual-memory PRODUCT_POLICY)
art_add_target_probe(
    NAME windows_w013_mspace_owner_probe STAGE w013 TYPE EXECUTABLE
    EXECUTION target-runnable TIMEOUT 60
    ${_art_windows_current_selector}
    SOURCES
        "${_art_test_cases_root}/mspace-owner/probe.cc"
        "${_art_test_repo_root}/vendor/art/runtime/gc/allocator/art-dlmalloc.cc"
    INCLUDE_DIRS
        "${_art_test_repo_root}/vendor/art/runtime"
        "${_art_test_repo_root}/vendor/art/libartbase"
        "${MDVM_NATIVE_SRC_ROOT_DIR}/external/dlmalloc"
    LINK_LIBRARIES artbase base log
    CONTRACTS allocator virtual-memory fatal-contract PRODUCT_POLICY
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/windows/mspace_owner_gate.py"
        --target-id "${ART_TARGET_ID}"
        --probe "$<TARGET_FILE:windows_w013_mspace_owner_probe>"
        --result
            "${CMAKE_CURRENT_BINARY_DIR}/results/w013-mspace-owner/result.json"
        --library-dir "${CMAKE_BINARY_DIR}"
        --library-dir "${_art_bundle_lib}/libcxx/bin"
        --timeout 8)
art_add_target_probe(
    NAME windows_w013_dlmalloc_config_probe STAGE w013 TYPE EXECUTABLE
    EXECUTION target-runnable TIMEOUT 60
    ${_art_windows_x86_64_msvc_selector}
    SOURCES "${_art_test_cases_root}/dlmalloc-config/probe.c"
    INCLUDE_DIRS "${MDVM_NATIVE_SRC_ROOT_DIR}/external/dlmalloc"
    LINK_LIBRARIES kernel32
    LINK_OPTIONS "${_art_no_cet}"
    CONTRACTS allocator configuration)
art_add_target_probe(
    NAME managed_w013_non_moving STAGE w013 TYPE MANAGED EXECUTION compile-only
    ${_art_non_moving_128m_ids_selector}
    SOURCES
        "${_art_test_cases_root}/non-moving-heap/W013NonMovingStressProbe.java"
    CONTRACTS allocator gc stress
    OUTPUT_NAME w013nonmovingstressprobe)
art_add_target_probe(
    NAME windows_w013_source_policy STAGE w013 TYPE GATE EXECUTION host-review
    ${_art_windows_current_selector}
    CONTRACTS allocator virtual-memory source-policy
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/windows/check_w013_source_policy.py")
foreach(_art_w013_heap_mib IN ITEMS 128 1024)
    # Preserve shared accepted pressure at 128 MiB; 1024 MiB remains the
    # separately accepted Windows resource-pressure profile.
    if(_art_w013_heap_mib EQUAL 128)
        set(_art_w013_non_moving_selector ${_art_non_moving_128m_ids_selector})
    else()
        set(_art_w013_non_moving_selector ${_art_windows_current_selector})
    endif()
    art_add_target_probe(
        NAME "managed_w013_non_moving_${_art_w013_heap_mib}m"
        STAGE w013 TYPE GATE EXECUTION target-runnable TIMEOUT 300
        ${_art_w013_non_moving_selector}
        DEPENDS managed_w013_non_moving dalvikvm icu_jni javacore openjdk
        CONTRACTS allocator gc stress runtime-load
        COMMAND
            "${Python3_EXECUTABLE}"
            "${_art_test_repo_root}/tests/support/runtime_gate.py"
            managed
            --target-id "${ART_TARGET_ID}"
            --dalvikvm "$<TARGET_FILE:dalvikvm>"
            --boot-jar "${_art_boot_jar}"
            --app-jar "${_art_managed_root}/w013nonmovingstressprobe.jar"
            --main-class W013NonMovingStressProbe
            --work-root
                "${CMAKE_CURRENT_BINARY_DIR}/results/w013-non-moving-${_art_w013_heap_mib}m"
            --icu-data "${_art_icu_data}"
            ${_art_managed_runtime_library_args}
            ${_art_target_runner_args}
            --vm-option=-Xint
            --vm-option=-Xmx${_art_w013_heap_mib}m
            --expect "nonmoving.total_bytes=75497472"
            --expect "nonmoving.stable=true"
            --expect "nonmoving.low=true"
            --expect "nonmoving.ok=true"
            --expect "W013NonMovingStressProbe.done=ok"
            --expect "main end exception=0"
            --forbid AssertionError
            --timeout 240)
endforeach()

# W-014: native thread-stack, guard-page, CET, and stack high-water contracts.
art_add_target_probe(
    NAME windows_w014_pthread_once_probe STAGE w014 TYPE EXECUTABLE
    EXECUTION target-runnable TIMEOUT 180 ${_art_windows_current_selector}
    SOURCES "${_art_test_cases_root}/pthread-once/probe.c"
    CONTRACTS threads PRODUCT_POLICY
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/runtime_gate.py"
        native
        --target-id "${ART_TARGET_ID}"
        --probe "$<TARGET_FILE:windows_w014_pthread_once_probe>"
        --work-root
            "${CMAKE_CURRENT_BINARY_DIR}/results/w014-pthread-once"
        --library-dir "${CMAKE_BINARY_DIR}"
        --library-dir "${_art_bundle_lib}/libcxx/bin"
        --expect "pthread_once_probe init_calls=1 failures=0 value=0x12345678"
        --expect "pthread_once_probe OK"
        --repeat 10
        --timeout 15)
art_add_target_probe(
    NAME win32_thread_stack_probe STAGE w014 TYPE EXECUTABLE
    EXECUTION target-runnable TIMEOUT 240 ${_art_windows_current_selector}
    SOURCES "${_art_test_cases_root}/thread-stack/probe.c"
    CONTRACTS stack threads PRODUCT_POLICY
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/runtime_gate.py"
        native
        --target-id "${ART_TARGET_ID}"
        --probe "$<TARGET_FILE:win32_thread_stack_probe>"
        --work-root
            "${CMAKE_CURRENT_BINARY_DIR}/results/w014-thread-stack"
        --library-dir "${CMAKE_BINARY_DIR}"
        --library-dir "${_art_bundle_lib}/libcxx/bin"
        --expect "win32_thread_stack_probe failures=0 join_stress=512 detach_stress=128"
        --expect "requested=65536"
        --expect "requested=262144"
        --expect "requested=1048576"
        --expect "requested=2097152"
        --expect "requested=9437184"
        --expect "win32_thread_stack_probe OK"
        --timeout 180)
art_add_target_probe(
    NAME win32_stack_page_probe STAGE w014 TYPE EXECUTABLE
    EXECUTION target-runnable TIMEOUT 240
    ${_art_windows_x86_64_msvc_selector}
    SOURCES
        "${_art_test_cases_root}/stack-page-growth/page_probe.cc"
        "${_art_test_cases_root}/stack-page-growth/fault_x86_64.S"
        "${_art_test_repo_root}/vendor/art/runtime/multiplatform/windows/stack_windows.cc"
    INCLUDE_DIRS "${_art_test_repo_root}/vendor/art/runtime/multiplatform/windows"
    CONTRACTS stack fault PRODUCT_POLICY
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/runtime_gate.py"
        native
        --target-id "${ART_TARGET_ID}"
        --probe "$<TARGET_FILE:win32_stack_page_probe>"
        --work-root
            "${CMAKE_CURRENT_BINARY_DIR}/results/w014-stack-page"
        --library-dir "${CMAKE_BINARY_DIR}"
        --library-dir "${_art_bundle_lib}/libcxx/bin"
        --expect "selection_cases count=8"
        --expect "reserved_case size=1048576 iterations=64"
        --expect "win32_stack_page_probe failures=0 committed_restore_iterations=64 reserved_restore_iterations=64 faults=258"
        --expect "win32_stack_page_probe OK"
        --timeout 180)
art_add_target_probe(
    NAME win32_stack_growth_probe STAGE w014 TYPE EXECUTABLE
    EXECUTION target-runnable TIMEOUT 900
    ${_art_windows_x86_64_msvc_selector}
    SOURCES
        "${_art_test_cases_root}/stack-page-growth/growth_probe.cc"
        "${_art_test_cases_root}/stack-page-growth/fault_x86_64.S"
        "${_art_test_repo_root}/vendor/art/runtime/multiplatform/windows/stack_windows.cc"
    INCLUDE_DIRS "${_art_test_repo_root}/vendor/art/runtime/multiplatform/windows"
    CONTRACTS stack fault PRODUCT_POLICY
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/runtime_gate.py"
        native-matrix
        --target-id "${ART_TARGET_ID}"
        --probe "$<TARGET_FILE:win32_stack_growth_probe>"
        --work-root
            "${CMAKE_CURRENT_BINARY_DIR}/results/w014-stack-growth"
        --library-dir "${CMAKE_BINARY_DIR}"
        --library-dir "${_art_bundle_lib}/libcxx/bin"
        --matrix
            "${_art_test_cases_root}/stack-page-growth/runtime-matrix.json")
art_add_target_probe(
    NAME win32_stack_growth_rx_probe STAGE w014 TYPE EXECUTABLE
    EXECUTION target-runnable TIMEOUT 120
    ${_art_windows_current_selector}
    SOURCES "${_art_test_cases_root}/stack-executable-memory/probe.c"
    CONTRACTS stack executable-memory
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/runtime_gate.py"
        native
        --target-id "${ART_TARGET_ID}"
        --probe "$<TARGET_FILE:win32_stack_growth_rx_probe>"
        --work-root
            "${CMAKE_CURRENT_BINARY_DIR}/results/w014-stack-growth-rx"
        --library-dir "${CMAKE_BINARY_DIR}"
        --library-dir "${_art_bundle_lib}/libcxx/bin"
        --expect "region label=before_rx valid=1"
        --expect "protect=0x20 protect_name=PAGE_EXECUTE_READ"
        --expect "terminal caught=0xc00000fd observed=0xc00000fd"
        --expect "marker label=before_rx readable=1 matching=64/64"
        --expect "recovery reset_attempted=1 reset_ok=1 restore_ok=1"
        --expect "win32_stack_growth_rx_probe failures=0"
        --expect "win32_stack_growth_rx_probe OK"
        --forbid "FAIL "
        --timeout 60)
art_add_target_probe(
    NAME win32_stack_pregrow_probe STAGE w014 TYPE EXECUTABLE
    EXECUTION target-runnable TIMEOUT 1200
    ${_art_windows_x86_64_msvc_selector}
    SOURCES
        "${_art_test_cases_root}/stack-pregrow/probe.c"
        "${_art_test_cases_root}/stack-pregrow/implicit_fault_x86_64.S"
    LINK_LIBRARIES psapi
    COMPILE_DEFINITIONS ${_art_windows_defines}
    CONTRACTS stack fault
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/runtime_gate.py"
        native-matrix
        --target-id "${ART_TARGET_ID}"
        --probe "$<TARGET_FILE:win32_stack_pregrow_probe>"
        --work-root
            "${CMAKE_CURRENT_BINARY_DIR}/results/w014-stack-pregrow"
        --library-dir "${CMAKE_BINARY_DIR}"
        --library-dir "${_art_bundle_lib}/libcxx/bin"
        --matrix
            "${_art_test_cases_root}/stack-pregrow/runtime-matrix.json")
art_add_target_probe(
    NAME win32_cet_policy_probe STAGE w014 TYPE EXECUTABLE
    EXECUTION target-runnable TIMEOUT 120
    ${_art_windows_current_selector}
    SOURCES
        "${_art_test_cases_root}/cet-stack-policy/probe.cc"
        "${_art_test_repo_root}/vendor/art/runtime/multiplatform/windows/cet_compat.cc"
    INCLUDE_DIRS "${_art_test_repo_root}/vendor/art/runtime/multiplatform/windows"
    CONTRACTS cet stack PRODUCT_POLICY
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/runtime_gate.py"
        native
        --target-id "${ART_TARGET_ID}"
        --probe "$<TARGET_FILE:win32_cet_policy_probe>"
        --work-root
            "${CMAKE_CURRENT_BINARY_DIR}/results/w014-cet-policy"
        --library-dir "${CMAKE_BINARY_DIR}"
        --library-dir "${_art_bundle_lib}/libcxx/bin"
        --expect "known_incompatible=0x00000000"
        --expect "WIN32_CET_POLICY_PROBE PASS"
        --forbid "WIN32_CET_POLICY_PROBE FAIL"
        --forbid "WIN32_CET_POLICY_PROBE REJECT"
        --timeout 60)
art_add_target_probe(
    NAME fs1stackhighwater STAGE w014 TYPE SHARED EXECUTION compile-only
    ${_art_windows_current_selector}
    SOURCES "${_art_test_cases_root}/stack-high-water/probe.cc"
    INCLUDE_DIRS "${_art_jni_include}"
    LINK_OPTIONS "${_art_no_cet}"
    CONTRACTS stack jni
    PREFIX lib WINDOWS_EXPORT_ALL_SYMBOLS)
if(ART_TEST_VARIANT STREQUAL "win32-stack-high-water")
    set(_art_fs1_structure_mode instrumented)
    if(CMAKE_BUILD_TYPE STREQUAL "Debug")
        set(_art_fs1_reserve 40960)
        set(_art_fs1_process_timeout 300)
        set(_art_fs1_ctest_timeout 1200)
    else()
        set(_art_fs1_reserve 8192)
        set(_art_fs1_process_timeout 180)
        set(_art_fs1_ctest_timeout 900)
    endif()
else()
    set(_art_fs1_structure_mode product)
endif()
art_add_target_probe(
    NAME win32_fs1_stack_high_water_structure STAGE w014 TYPE GATE
    EXECUTION host-review
    ${_art_windows_current_selector}
    DEPENDS art
    CONTRACTS stack codegen source-policy
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/windows/fs1_stack_high_water_structure.py"
        --mode "${_art_fs1_structure_mode}"
        --repo "${_art_test_repo_root}"
        --build "${CMAKE_BINARY_DIR}"
        --llvm-readobj
            "${ART_LLVM_READOBJ}"
        --llvm-objdump
            "${ART_LLVM_OBJDUMP}")
if(ART_TEST_VARIANT STREQUAL "win32-stack-high-water")
    art_add_target_probe(
        NAME managed_fs1_stack_high_water STAGE w014 TYPE MANAGED
        EXECUTION target-runnable TIMEOUT "${_art_fs1_ctest_timeout}"
        ${_art_windows_current_selector}
        SOURCES
            "${_art_test_cases_root}/stack-high-water/FS1StackHighWaterProbe.java"
        CONTRACTS stack jni
        OUTPUT_NAME fs1stackhighwaterprobe
        DEPENDS
            fs1stackhighwater dalvikvm icu_jni javacore openjdk
        COMMAND
            "${Python3_EXECUTABLE}"
            "${_art_test_repo_root}/tests/support/windows/fs1_stack_high_water_gate.py"
            --target-id "${ART_TARGET_ID}"
            --dalvikvm "$<TARGET_FILE:dalvikvm>"
            --boot-jar "${_art_boot_jar}"
            --app-jar
                "${_art_managed_root}/fs1stackhighwaterprobe.jar"
            --work-root
                "${CMAKE_CURRENT_BINARY_DIR}/results/w014-stack-high-water"
            --icu-data "${_art_icu_data}"
            --jni-dir "$<TARGET_FILE_DIR:fs1stackhighwater>"
            --library-dir "$<TARGET_FILE_DIR:dalvikvm>"
            --library-dir "${_art_bundle_lib}/libcxx/bin"
            --validator
                "${_art_test_repo_root}/tests/support/windows/fs1_stack_high_water_check.py"
            --art-reserve "${_art_fs1_reserve}"
            --timeout "${_art_fs1_process_timeout}")
else()
    art_add_target_probe(
        NAME managed_fs1_stack_high_water STAGE w014 TYPE MANAGED
        EXECUTION compile-only
        ${_art_windows_current_selector}
        SOURCES
            "${_art_test_cases_root}/stack-high-water/FS1StackHighWaterProbe.java"
        CONTRACTS stack jni
        OUTPUT_NAME fs1stackhighwaterprobe
        DEPENDS fs1stackhighwater)
endif()

# W-025: JIT section policy and PE unwind registration/lifecycle.
art_add_target_probe(
    NAME win32_jit_unwind_info_probe STAGE w025 TYPE EXECUTABLE
    EXECUTION target-runnable TIMEOUT 120
    ${_art_windows_x86_64_msvc_selector}
    SOURCES "${_art_test_cases_root}/jit-unwind-info/probe.cc"
    INCLUDE_DIRS "${_art_test_repo_root}/vendor/art/compiler"
    CONTRACTS jit unwind PRODUCT_POLICY
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/runtime_gate.py"
        native
        --target-id "${ART_TARGET_ID}"
        --probe "$<TARGET_FILE:win32_jit_unwind_info_probe>"
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/w025-unwind-info"
        --library-dir "${CMAKE_BINARY_DIR}"
        --library-dir "${_art_bundle_lib}/libcxx/bin"
        --expect "win32_jit_unwind_info_probe failures=0 cases=6"
        --expect "win32_jit_unwind_info_probe OK"
        --forbid "FAIL:"
        --timeout 60)
art_add_target_probe(
    NAME win32_jit_unwind_registry_probe STAGE w025 TYPE EXECUTABLE
    EXECUTION target-runnable TIMEOUT 120
    ${_art_windows_x86_64_msvc_selector}
    SOURCES
        "${_art_test_cases_root}/jit-unwind-registry/probe.cc"
        "${_art_test_repo_root}/vendor/art/runtime/multiplatform/windows/jit_unwind_windows.cc"
    INCLUDE_DIRS
        "${_art_test_repo_root}/vendor/art"
        "${_art_test_repo_root}/vendor/art/compiler"
        "${_art_test_repo_root}/vendor/art/libartbase"
    LINK_LIBRARIES artbase base log
    CONTRACTS jit unwind PRODUCT_POLICY
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/runtime_gate.py"
        native
        --target-id "${ART_TARGET_ID}"
        --probe "$<TARGET_FILE:win32_jit_unwind_registry_probe>"
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/w025-unwind-registry"
        --library-dir "${CMAKE_BINARY_DIR}"
        --library-dir "${_art_bundle_lib}/libcxx/bin"
        --expect "win32_jit_unwind_registry_probe failures=0"
        --expect "win32_jit_unwind_registry_probe OK"
        --forbid "FAIL:"
        --timeout 60)
art_add_target_probe(
    NAME jitunwindlifecycleprobe STAGE w025 TYPE SHARED EXECUTION compile-only
    ${_art_windows_x86_64_msvc_selector}
    SOURCES "${_art_test_cases_root}/jit-unwind-lifecycle/probe.cc"
    LINK_LIBRARIES art
    COMPILE_OPTIONS
        -fno-rtti -Wno-thread-safety -Wno-unused-command-line-argument
        -Wno-microsoft-cast -Wno-invalid-offsetof
    COMPILE_DEFINITIONS ART_CONSUMING_LIBART
    CONTRACTS jit unwind
    PREFIX lib OUTPUT_NAME jitunwindlifecycleprobe WINDOWS_EXPORT_ALL_SYMBOLS PRODUCT_POLICY)
art_add_target_probe(
    NAME w025jitlifecyclestressprobe STAGE w025 TYPE SHARED EXECUTION compile-only
    ${_art_windows_x86_64_msvc_selector}
    SOURCES "${_art_test_cases_root}/jit-lifecycle-stress/probe.cc"
    LINK_LIBRARIES art
    COMPILE_OPTIONS
        -fno-rtti -Wno-thread-safety -Wno-unused-command-line-argument
        -Wno-microsoft-cast -Wno-invalid-offsetof
    COMPILE_DEFINITIONS ART_CONSUMING_LIBART
    CONTRACTS jit unwind stress
    PREFIX lib OUTPUT_NAME w025jitlifecyclestressprobe WINDOWS_EXPORT_ALL_SYMBOLS PRODUCT_POLICY)
art_add_target_probe(
    NAME w025jitmappingprobe STAGE w025 TYPE SHARED EXECUTION compile-only
    ${_art_windows_current_selector}
    SOURCES "${_art_test_cases_root}/jit-mapping/probe.cc"
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
art_add_target_probe(
    NAME managed_jit_unwind_lifecycle STAGE w025 TYPE MANAGED
    EXECUTION target-runnable TIMEOUT 600
    ${_art_windows_x86_64_msvc_selector}
    SOURCES
        "${_art_test_cases_root}/jit-unwind-lifecycle/JitUnwindLifecycleProbe.java"
    DEPENDS jitunwindlifecycleprobe dalvikvm icu_jni javacore openjdk openjdkjvm
    CONTRACTS jit unwind
    OUTPUT_NAME jitunwindlifecycleprobe
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_cases_root}/jit-unwind-lifecycle/run.py"
        --target-id "${ART_TARGET_ID}"
        --probe "$<TARGET_FILE:jitunwindlifecycleprobe>"
        --dalvikvm "$<TARGET_FILE:dalvikvm>"
        --boot-jar "${_art_boot_jar}"
        --app-jar "${_art_managed_root}/jitunwindlifecycleprobe.jar"
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/w025-unwind-lifecycle"
        --icu-data "${_art_icu_data}"
        ${_art_managed_runtime_library_args})
art_add_target_probe(
    NAME managed_w025_jit_lifecycle_stress STAGE w025
    TYPE MANAGED EXECUTION target-runnable TIMEOUT 1200
    ${_art_windows_x86_64_msvc_selector}
    SOURCES
        "${_art_test_cases_root}/jit-lifecycle-stress/W025JitLifecycleStressProbe.java"
    DEPENDS w025jitlifecyclestressprobe dalvikvm icu_jni javacore openjdk openjdkjvm
    CONTRACTS jit unwind stress
    OUTPUT_NAME w025jitlifecyclestressprobe
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_cases_root}/jit-lifecycle-stress/run.py"
        --target-id "${ART_TARGET_ID}"
        --probe "$<TARGET_FILE:w025jitlifecyclestressprobe>"
        --dalvikvm "$<TARGET_FILE:dalvikvm>"
        --boot-jar "${_art_boot_jar}"
        --app-jar "${_art_managed_root}/w025jitlifecyclestressprobe.jar"
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/w025-lifecycle-stress"
        --icu-data "${_art_icu_data}"
        ${_art_managed_runtime_library_args})
art_add_target_probe(
    NAME managed_w025_jit_mapping STAGE w025 TYPE MANAGED
    EXECUTION target-runnable TIMEOUT 1200
    ${_art_windows_current_selector}
    SOURCES "${_art_test_cases_root}/jit-mapping/W025JitMappingProbe.java"
    DEPENDS w025jitmappingprobe dalvikvm icu_jni javacore openjdk openjdkjvm
    CONTRACTS jit virtual-memory
    OUTPUT_NAME w025jitmappingprobe
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_cases_root}/jit-mapping/run.py"
        --target-id "${ART_TARGET_ID}"
        --probe "$<TARGET_FILE:w025jitmappingprobe>"
        --dalvikvm "$<TARGET_FILE:dalvikvm>"
        --boot-jar "${_art_boot_jar}"
        --app-jar "${_art_managed_root}/w025jitmappingprobe.jar"
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/w025-jit-mapping"
        --icu-data "${_art_icu_data}"
        ${_art_managed_runtime_library_args})
art_add_target_probe(
    NAME windows_w025_section_policy_probe STAGE w025 TYPE EXECUTABLE
    EXECUTION target-runnable TIMEOUT 900 ${_art_windows_current_selector}
    SOURCES "${_art_test_cases_root}/jit-section-policy/probe.cc"
    LINK_LIBRARIES onecore psapi
    COMPILE_OPTIONS -Xclang -cfguard
    LINK_OPTIONS "LINKER:/guard:cf"
    CONTRACTS jit executable-memory cfg
    OUTPUT_NAME W025SectionPolicyProbe PRODUCT_POLICY
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/runtime_gate.py"
        native-matrix
        --target-id "${ART_TARGET_ID}"
        --probe "$<TARGET_FILE:windows_w025_section_policy_probe>"
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/w025-section-policy"
        --library-dir "${CMAKE_BINARY_DIR}"
        --library-dir "${_art_bundle_lib}/libcxx/bin"
        --matrix "${_art_test_cases_root}/jit-section-policy/runtime-matrix.json")
art_add_target_probe(
    NAME windows_w025_policy_launcher STAGE w025 TYPE EXECUTABLE
    EXECUTION target-runnable TIMEOUT 1200 ${_art_windows_current_selector}
    SOURCES "${_art_test_cases_root}/jit-section-policy/launcher.cc"
    DEPENDS
        windows_w025_section_policy_probe
        managed_w025_jit_mapping managed_imageless_hello
        dalvikvm icu_jni javacore openjdk openjdkjvm
    CONTRACTS jit process-policy
    OUTPUT_NAME W025PolicyLauncher PRODUCT_POLICY
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_cases_root}/jit-section-policy/run.py"
        --target-id "${ART_TARGET_ID}"
        --launcher "$<TARGET_FILE:windows_w025_policy_launcher>"
        --section-probe "$<TARGET_FILE:windows_w025_section_policy_probe>"
        --mapping-probe "$<TARGET_FILE:w025jitmappingprobe>"
        --dalvikvm "$<TARGET_FILE:dalvikvm>"
        --boot-jar "${_art_boot_jar}"
        --mapping-jar "${_art_managed_root}/w025jitmappingprobe.jar"
        --hello-jar "${_art_managed_root}/hello.jar"
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/w025-policy-launcher"
        --icu-data "${_art_icu_data}"
        ${_art_managed_runtime_library_args})
art_add_target_probe(
    NAME windows_w025_jit_runtime_controls STAGE w025 TYPE GATE
    EXECUTION target-runnable TIMEOUT 1800
    ${_art_windows_x86_64_msvc_selector}
    DEPENDS
        managed_imageless_hello managed_math_critical managed_ioprobe
        managed_netprobe managed_gcprobe managed_throwprobe
        dalvikvm icu_jni javacore openjdk
    CONTRACTS jit runtime-load control-policy
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_cases_root}/jit-runtime-controls/run.py"
        --target-id "${ART_TARGET_ID}"
        --dalvikvm "$<TARGET_FILE:dalvikvm>"
        --boot-jar "${_art_boot_jar}"
        --hello-jar "${_art_managed_root}/hello.jar"
        --math-jar "${_art_managed_root}/mathcriticalprobe.jar"
        --io-jar "${_art_managed_root}/ioprobe.jar"
        --net-jar "${_art_managed_root}/netprobe.jar"
        --gc-jar "${_art_managed_root}/gcprobe.jar"
        --throw-jar "${_art_managed_root}/throwprobe.jar"
        --work-root "${CMAKE_CURRENT_BINARY_DIR}/results/w025-jit-controls"
        --icu-data "${_art_icu_data}"
        ${_art_managed_runtime_library_args})
art_add_target_probe(
    NAME windows_w025_jit_structure STAGE w025 TYPE GATE
    EXECUTION host-review ${_art_windows_current_selector}
    DEPENDS
        art windows_w025_section_policy_probe
        w025jitlifecyclestressprobe
    CONTRACTS jit virtual-memory unwind source-policy
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/windows/check_w025_jit_contract.py"
        --target-id "${ART_TARGET_ID}"
        --repo "${_art_test_repo_root}"
        --art "$<TARGET_FILE:art>"
        --section-probe "$<TARGET_FILE:windows_w025_section_policy_probe>"
        --stress-probe "$<TARGET_FILE:w025jitlifecyclestressprobe>"
        --llvm-readobj "${ART_LLVM_READOBJ}"
        --result
            "${CMAKE_CURRENT_BINARY_DIR}/results/w025-structure/result.json")

# W-027: reject ANSI Win32 entry points in every active Windows translation
# unit while classifying JNI's unrelated Call*MethodA family explicitly.
art_add_target_probe(
    NAME windows_w027_unicode_api_policy STAGE w027 TYPE GATE
    EXECUTION host-review ${_art_windows_current_selector}
    DEPENDS art
    CONTRACTS unicode win32-api source-policy
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tests/support/windows/check_win32_unicode_api_policy.py"
        --repo "${_art_test_repo_root}"
        --compile-commands "${CMAKE_BINARY_DIR}/compile_commands.json")

# W-028 begins boot-only Windows AOT implementation with a native compiler
# operation gate. It deliberately produces no ART image: ImageWriter and the
# executable OAT loader belong to later milestones.
art_add_target_probe(
    NAME windows_w028_dex2oat_no_image STAGE w028 TYPE GATE
    EXECUTION target-runnable TIMEOUT 900
    ${_art_windows_x86_64_msvc_selector}
    DEPENDS dex2oat art-managed-boot-jar managed_imageless_hello
    CONTRACTS aot oat vdex dex2oat elf-layout
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_test_repo_root}/tools/run_dex2oat_no_image.py"
        --target-id "${ART_TARGET_ID}"
        --dex2oat "$<TARGET_FILE:dex2oat>"
        --boot-jar "${_art_boot_jar}"
        --input-jar "${_art_managed_root}/hello.jar"
        --output-root
            "${CMAKE_CURRENT_BINARY_DIR}/results/w028-dex2oat-no-image"
        --instruction-set x86_64
        --library-dir "$<TARGET_FILE_DIR:dex2oat>"
        --library-dir "${ART_TARGET_BUNDLE_ROOT}/lib/libcxx/bin"
        --parallel 2
        --timeout 600)

# W-029 begins the stable generation/startup identity step without claiming a
# boot image exists. It freezes the single-component package contract and
# rejects case, separator, physical-path, and component-count mismatches.
art_add_target_probe(
    NAME windows_w029_aot_identity STAGE w029 TYPE GATE
    EXECUTION host-review
    ${_art_windows_x86_64_msvc_selector}
    CONTRACTS aot boot-image identity packaging
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_windows_aot_identity}"
        --target-id "${ART_TARGET_ID}"
        --result
            "${CMAKE_CURRENT_BINARY_DIR}/results/w029-aot-identity/result.json")

# W-030 first verifies the private-copy primitive independently of the loader.
art_add_target_probe(
    NAME windows_w030_private_copy_probe STAGE w030 TYPE EXECUTABLE
    EXECUTION target-runnable TIMEOUT 60
    ${_art_windows_x86_64_msvc_selector}
    SOURCES "${_art_test_cases_root}/aot-private-copy/probe.cc"
    INCLUDE_DIRS "${_art_test_repo_root}/vendor/art/libartbase"
    LINK_LIBRARIES artbase base log
    CONTRACTS aot elf-loader private-copy virtual-memory)
# It then generates the first boot-only Windows image, stages the accepted
# W-029 package topology, and starts ART from the package root with the exact
# relative -Ximage value. The runner rejects identity drift before process
# creation and fails if ART silently falls back to its imageless path.
art_add_target_probe(
    NAME windows_w030_boot_image_startup STAGE w030 TYPE GATE
    EXECUTION target-runnable TIMEOUT 1800
    ${_art_windows_x86_64_msvc_selector}
    DEPENDS
        art-runtime-boot-image
        managed_imageless_hello
        dalvikvm
        icu_jni
        javacore
        openjdk
    CONTRACTS aot boot-image identity packaging runtime-load elf-loader
    COMMAND
        "${Python3_EXECUTABLE}"
        "${_art_windows_boot_image_runner}"
        --target-id "${ART_TARGET_ID}"
        --dalvikvm "$<TARGET_FILE:dalvikvm>"
        --boot-jar "${_art_boot_jar}"
        --app-jar "${_art_managed_root}/hello.jar"
        --boot-image-dir "${_art_boot_image_root}"
        --icu-data "${_art_icu_data}"
        --work-root
            "${CMAKE_CURRENT_BINARY_DIR}/results/w030-boot-image-startup"
        ${_art_managed_runtime_library_args}
        --timeout 600)

get_property(_art_test_catalog_records GLOBAL PROPERTY ART_TEST_CATALOG_RECORDS)
string(JOIN ",\n" _art_test_catalog_body ${_art_test_catalog_records})
set(_art_test_catalog "${CMAKE_CURRENT_BINARY_DIR}/art_test_catalog.json")
file(WRITE "${_art_test_catalog}"
    "{\n"
    "  \"schema_version\": 1,\n"
    "  \"target_id\": \"${ART_TARGET_ID}\",\n"
    "  \"target_platform\": \"${ART_TARGET_PLATFORM}\",\n"
    "  \"target_arch\": \"${ART_TARGET_ARCH}\",\n"
    "  \"target_abi\": \"${ART_TARGET_ABI}\",\n"
    "  \"probes\": [\n${_art_test_catalog_body}\n  ]\n"
    "}\n")
