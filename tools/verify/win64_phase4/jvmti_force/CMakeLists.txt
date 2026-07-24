cmake_minimum_required(VERSION 3.20)
project(Win64JvmtiForceProbe C)

if(NOT CMAKE_C_COMPILER_ID MATCHES "Clang")
  message(FATAL_ERROR "Need LLVM clang (got ${CMAKE_C_COMPILER_ID})")
endif()

get_filename_component(_repo "${CMAKE_CURRENT_SOURCE_DIR}/../../../.." ABSOLUTE)
set(MDVM_REPO_ROOT "${_repo}" CACHE PATH "Repository root")

add_library(jvmtiforceprobe SHARED jvmti_force_probe.c)
target_include_directories(jvmtiforceprobe PRIVATE
  "${MDVM_REPO_ROOT}/vendor/libnativehelper/include_jni"
  "${MDVM_REPO_ROOT}/vendor/art/openjdkjvmti/include")
target_compile_definitions(jvmtiforceprobe PRIVATE
  _CRT_SECURE_NO_WARNINGS NOMINMAX WIN32_LEAN_AND_MEAN NOGDI)
set_target_properties(jvmtiforceprobe PROPERTIES
  OUTPUT_NAME libjvmtiforceprobe
  WINDOWS_EXPORT_ALL_SYMBOLS ON)
