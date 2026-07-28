cmake_minimum_required(VERSION 3.20)
project(windows_x64_critical_native_probe C)

add_link_options("LINKER:/CETCOMPAT:NO")

if(NOT MDVM_REPO_ROOT)
  message(FATAL_ERROR "MDVM_REPO_ROOT is required")
endif()

add_library(criticalnativeprobe SHARED critical_native_probe.c)
target_include_directories(criticalnativeprobe PRIVATE
  "${MDVM_REPO_ROOT}/vendor/libnativehelper/include_jni")
set_target_properties(criticalnativeprobe PROPERTIES
  PREFIX "lib"
  OUTPUT_NAME "criticalnativeprobe"
  WINDOWS_EXPORT_ALL_SYMBOLS ON)
