#include "export/jit_create.h"

// Keep the Windows DLL ABI small and intentional. The runtime's C++ ABI is
// private; this C entry point is the stable probe/loader contract.
extern "C" art::jit::JitCompilerInterface* art_compiler_jit_create() {
    return art::jit::jit_create();
}
