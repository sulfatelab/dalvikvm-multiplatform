/* Narrow MS-compatible lookup shim for the pinned ART OatKeyValueStore. */
#pragma once

#if !defined(_WIN32)
#error "mdvm_windows_oat_writer_compat.h is for Windows targets only"
#endif

namespace art {
namespace linker {
class OatWriter;
}  // namespace linker
}  // namespace art
