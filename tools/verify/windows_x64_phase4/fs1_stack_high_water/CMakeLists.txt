cmake_minimum_required(VERSION 3.20)
project(windows_x64_fs1_stack_high_water CXX)

add_link_options("LINKER:/CETCOMPAT:NO")

if(NOT MDVM_REPO_ROOT)
  message(FATAL_ERROR "MDVM_REPO_ROOT is required")
endif()

add_library(fs1stackhighwater SHARED fs1_stack_high_water_probe.cc)
target_include_directories(fs1stackhighwater PRIVATE
  "${MDVM_REPO_ROOT}/vendor/libnativehelper/include_jni")
set_target_properties(fs1stackhighwater PROPERTIES
  PREFIX "lib"
  OUTPUT_NAME "fs1stackhighwater"
  WINDOWS_EXPORT_ALL_SYMBOLS ON)
