cmake_minimum_required(VERSION 3.20)
project(win64_w003_frame_probe C)

if(NOT MDVM_REPO_ROOT)
  message(FATAL_ERROR "MDVM_REPO_ROOT is required")
endif()

add_library(w003frameprobe SHARED w003_frame_probe.c)
target_include_directories(w003frameprobe PRIVATE
  "${MDVM_REPO_ROOT}/vendor/libnativehelper/include_jni")
set_target_properties(w003frameprobe PROPERTIES
  PREFIX "lib"
  OUTPUT_NAME "w003frameprobe"
  WINDOWS_EXPORT_ALL_SYMBOLS ON)
