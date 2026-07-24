cmake_minimum_required(VERSION 3.20)
project(win64_native_abi_probe C)

if(NOT MDVM_REPO_ROOT)
  message(FATAL_ERROR "MDVM_REPO_ROOT is required")
endif()

add_library(nativeabiprobe SHARED native_abi_probe.c)
target_include_directories(nativeabiprobe PRIVATE
  "${MDVM_REPO_ROOT}/vendor/libnativehelper/include_jni")
set_target_properties(nativeabiprobe PROPERTIES
  PREFIX "lib"
  OUTPUT_NAME "nativeabiprobe"
  WINDOWS_EXPORT_ALL_SYMBOLS ON)
