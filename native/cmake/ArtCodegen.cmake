# Configure-time ART generated-source ownership for the common product graph.
# operator_out commands live in the generated graph; this module owns aconfig,
# mterp, asm_defines, and the Windows PE header projections.

file(GLOB _mdvm_mterp_inputs
    "${MDVM_ART_ROOT_DIR}/art/runtime/interpreter/mterp/${ART_TARGET_MTERP_SOURCE_DIR}/*.S")
file(GLOB _mdvm_asm_define_inputs
    "${MDVM_ART_ROOT_DIR}/art/tools/cpp-define-generator/*.def")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    ${_mdvm_mterp_inputs}
    ${_mdvm_asm_define_inputs}
    "${MDVM_ART_ROOT_DIR}/art/runtime/interpreter/mterp/gen_mterp.py"
    "${MDVM_ART_ROOT_DIR}/art/runtime/interpreter/mterp/common/gen_setup.py"
    "${MDVM_ART_ROOT_DIR}/art/tools/cpp-define-generator/asm_defines.cc"
    "${MDVM_ART_ROOT_DIR}/art/tools/cpp-define-generator/make_header.py"
    "${MDVM_BP2CMAKE}/bp2cmake/codegen.py"
    "${MDVM_BP2CMAKE}/bp2cmake/codegen_main.py")
set(_art_codegen_options)
if(ART_TARGET_PLATFORM STREQUAL "windows")
    list(APPEND _art_codegen_options --os windows)
    execute_process(
        COMMAND ${CMAKE_CXX_COMPILER} -print-resource-dir
        OUTPUT_VARIABLE _art_clang_resource_dir
        OUTPUT_STRIP_TRAILING_WHITESPACE
        RESULT_VARIABLE _art_resource_rc)
    if(NOT _art_resource_rc EQUAL 0)
        message(FATAL_ERROR "cannot query the selected Clang resource directory")
    endif()
    # Normalize native Windows Clang's backslash spelling before this value is
    # embedded in later SHELL:-isystem options for the GNU-style driver.
    file(TO_CMAKE_PATH "${_art_clang_resource_dir}" _art_clang_resource_dir)
    foreach(_art_codegen_include
            "${ART_TARGET_BUNDLE_ROOT}/lib/libcxx/include/c++/v1"
            "${_art_clang_resource_dir}/include"
            "${ART_TARGET_BUNDLE_ROOT}/xwin/sdk/include/ucrt"
            "${ART_TARGET_BUNDLE_ROOT}/xwin/sdk/include/shared"
            "${ART_TARGET_BUNDLE_ROOT}/xwin/sdk/include/um"
            "${ART_TARGET_BUNDLE_ROOT}/xwin/crt/include")
        if(EXISTS "${_art_codegen_include}")
            list(APPEND _art_codegen_options --target-include "${_art_codegen_include}")
        endif()
    endforeach()
endif()
if(ART_TEST_VARIANT STREQUAL "win32-stack-high-water")
    list(APPEND _art_codegen_options --asm-define ART_WIN32_STACK_HIGH_WATER=1)
endif()
set(_art_codegen_kinds aconfig mterp asm_defines)
if(ART_TARGET_PLATFORM STREQUAL "windows")
    list(APPEND _art_codegen_kinds windows_pe_headers)
endif()
foreach(_kind IN LISTS _art_codegen_kinds)
    execute_process(
        COMMAND ${CMAKE_COMMAND} -E env "PYTHONPATH=${MDVM_BP2CMAKE}"
                ${Python3_EXECUTABLE} -m bp2cmake.codegen_main
                --root ${MDVM_NATIVE_SRC_ROOT_DIR} --art-root ${MDVM_ART_ROOT_DIR}
                --libcore-root ${MDVM_LIBCORE_DIR}
                --gensrc ${MDVM_GENSRC_DIR}
                --arch ${ART_TARGET_AOSP_ARCH} --clang ${CMAKE_CXX_COMPILER}
                --target-triple ${ART_TARGET_TRIPLE}
                --mterp-source-dir ${ART_TARGET_MTERP_SOURCE_DIR}
                --mterp-output ${ART_TARGET_MTERP_OUTPUT}
                ${_art_codegen_options} --only ${_kind}
        RESULT_VARIABLE _rc)
    if(NOT _rc EQUAL 0)
        message(FATAL_ERROR "codegen '${_kind}' failed (${_rc})")
    endif()
endforeach()
