// Explicit compatibility for pinned ART sources that use bionic's global
// nullptr_t spelling. Apply only to reviewed source files; do not use this as
// a product-wide prelude.
#pragma once

#ifndef __cplusplus
#error "mdvm_bionic_nullptr_compat.h requires C++"
#endif

#include <cstddef>

using std::nullptr_t;
