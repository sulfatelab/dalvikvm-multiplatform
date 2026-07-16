// Toolchain-compat prelude — harness force-include ONLY, NOT a source edit.
//
// clang-21 / newer libc++ stopped transitively pulling these in, so some 2023
// AOSP TUs that use uint*_t / std::copy_n without an explicit include fail.
// Force-including this one header via a single -include keeps the CMake
// set_source_files_properties simple (one flag, one arg — no repeated -include
// that CMake de-duplicates). Vanishes on submodule bump. See toolchain-drift
// memory. Never force-included before files with deliberate macro ordering
// (e.g. libbase/posix_strerror_r.cpp's #undef _GNU_SOURCE).
// Use the C-compatible spellings so this prelude works when force-included into
// BOTH C and C++ TUs (libart pulls in cpu_features .c files). <cstdint> etc. are
// C++-only; <stdint.h>/<stddef.h> are valid in C and C++.
#include <stdint.h>
#include <stddef.h>
#if defined(__cplusplus)
#include <algorithm>
#include <optional>
#include <cstring>
#include <climits>
#include <ctime>
#include <limits>
#include <cstdint>
#include <cstddef>
#include <csignal>
#include <cmath>
#include <filesystem>
#endif
