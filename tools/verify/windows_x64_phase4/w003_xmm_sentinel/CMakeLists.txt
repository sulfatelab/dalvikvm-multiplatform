cmake_minimum_required(VERSION 3.20)
project(windows_x64_w003_xmm_sentinel C ASM)

add_link_options("LINKER:/CETCOMPAT:NO")

if(NOT MDVM_REPO_ROOT)
  message(FATAL_ERROR "MDVM_REPO_ROOT is required")
endif()

add_library(w003xmmsentinel SHARED
  w003_xmm_sentinel.c
  w003_xmm_sentinel_x86_64.S)
target_include_directories(w003xmmsentinel PRIVATE
  "${MDVM_REPO_ROOT}/vendor/libnativehelper/include_jni")
set_target_properties(w003xmmsentinel PROPERTIES
  PREFIX "lib"
  OUTPUT_NAME "w003xmmsentinel"
  WINDOWS_EXPORT_ALL_SYMBOLS ON)
