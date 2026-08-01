// Explicit PE ownership for inline template specializations used by ART
// translation units that intentionally include declarations without the
// corresponding -inl headers. Class-level dllexport makes these DLL-owned;
// optimized builds otherwise inline away the only producer definitions.

#include "art_method-inl.h"
#include "mirror/object-inl.h"

namespace art {

template ObjPtr<mirror::Class> ArtMethod::GetDeclaringClass<kWithReadBarrier>();

namespace mirror {

template void Object::SetField32<false, false, kVerifyNone, false>(MemberOffset, int32_t);
template void Object::SetField32<false, true, kVerifyNone, false>(MemberOffset, int32_t);

}  // namespace mirror
}  // namespace art
