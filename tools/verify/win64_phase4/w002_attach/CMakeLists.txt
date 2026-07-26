cmake_minimum_required(VERSION 3.20)
project(win64_w002_attach_probe C)

add_link_options("LINKER:/CETCOMPAT:NO")

if(NOT MDVM_REPO_ROOT)
  message(FATAL_ERROR "MDVM_REPO_ROOT is required")
endif()

add_library(w002attachprobe SHARED w002_attach_probe.c)
target_include_directories(w002attachprobe PRIVATE
  "${MDVM_REPO_ROOT}/vendor/libnativehelper/include_jni")
set_target_properties(w002attachprobe PROPERTIES
  PREFIX "lib"
  OUTPUT_NAME "w002attachprobe"
  WINDOWS_EXPORT_ALL_SYMBOLS ON)
