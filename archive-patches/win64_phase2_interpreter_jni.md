# Win64 Phase 2 — Interpreter JNI helpers (A3)

**File (vendor, gitignored):** `vendor/art/runtime/interpreter/interpreter.cc`  
**Date:** 2026-07-16  
**Gate:** Phase 2 A3 Hello.main (wine64 imageless `-Xint`)

## Why

Win64 PE builds cannot use ART quick JNI / `art_jni_dlsym_lookup_stub` (SysV + `%gs` Thread TLS).
Phase 2 routes natives through C++ `InterpreterJni` / `InterpreterJniGeneric`.

## Apply

Re-apply or merge the helpers below into `interpreter.cc` if the vendor tree is reset.
Also ensure specialized `FI`/`DJ` paths use `SetF`/`SetD` (not raw int/long bit stores).

Key shorties needed for Hello:

- `FJ` — NativeConverter.getAveBytesPerChar / getAveCharsPerByte
- `IJ` / `VJ` / `JL` / `LJ` / `VLJ` / `VJL` / `VJIIL` / `IJLILILZ` — converter open/close/encode/decode/register
- integer/object generic packing for remaining PE stubs

## Source excerpt (as of A3 pass)

```cpp
// Resolve ArtMethod JNI entrypoint without using art_jni_dlsym_lookup_stub
// (that stub needs %gs Thread TLS and a quick frame, neither available on Win64 -Xint).
static void* ResolveJniEntryPoint(Thread* self, ArtMethod* method)
    REQUIRES_SHARED(Locks::mutator_lock_) {
  ClassLinker* class_linker = Runtime::Current()->GetClassLinker();
  const void* native_code = class_linker->GetRegisteredNative(self, method);
  if (native_code != nullptr) {
    return const_cast<void*>(native_code);
  }
  void* entry = method->GetEntryPointFromJni();
  if (!class_linker->IsJniDlsymLookupStub(entry) &&
      !class_linker->IsJniDlsymLookupCriticalStub(entry)) {
    return entry;
  }
  JavaVMExt* vm = down_cast<JNIEnvExt*>(self->GetJniEnv())->GetVm();
  std::string error_msg;
  native_code = vm->FindCodeForNativeMethod(method, &error_msg, /*can_suspend=*/ true);
  if (native_code == nullptr) {
    LOG(ERROR) << error_msg;
    self->ThrowNewException("Ljava/lang/UnsatisfiedLinkError;", error_msg.c_str());
    return nullptr;
  }
  return const_cast<void*>(class_linker->RegisterNative(self, method, native_code));
}

// Generic JNI invoker for integer/object shorties when no specialized case exists.
// Packs JNIEnv*, (jclass|jobject), and Java args into up to 8 integer/pointer slots and
// calls the native function via a uniform C prototype. Sufficient for Win64 Phase-2
// where quick generic-JNI asm is not yet ABI/GS-safe. Floating-point shorties are not handled.
static bool InterpreterJniGeneric(Thread* self,
                                  ArtMethod* method,
                                  std::string_view shorty,
                                  ObjPtr<mirror::Object> receiver,
                                  uint32_t* args,
                                  JValue* result)
    REQUIRES_SHARED(Locks::mutator_lock_) {
  void* jni_code = ResolveJniEntryPoint(self, method);
  if (jni_code == nullptr) {
    return true;  // exception pending
  }

  if (method->IsCriticalNative()) {
    // Critical natives omit JNIEnv*/jclass; only handle simple cases here.
    if (shorty == "II") {
      using fntype = jint(jint);
      auto* fn = reinterpret_cast<fntype*>(jni_code);
      result->SetI(fn(static_cast<jint>(args[0])));
      return true;
    }
    if (shorty == "I") {
      using fntype = jint();
      auto* fn = reinterpret_cast<fntype*>(jni_code);
      result->SetI(fn());
      return true;
    }
    if (shorty == "Z") {
      using fntype = jboolean();
      auto* fn = reinterpret_cast<fntype*>(jni_code);
      result->SetZ(fn());
      return true;
    }
    if (shorty == "ZI") {
      using fntype = jboolean(jint);
      auto* fn = reinterpret_cast<fntype*>(jni_code);
      result->SetZ(fn(static_cast<jint>(args[0])));
      return true;
    }
    return false;
  }

  // Handle float/double and common NativeConverter shorties (Win64 -Xint).
  auto jlong_arg0 = [&]() -> jlong {
    return static_cast<jlong>((static_cast<uint64_t>(args[1]) << 32) |
                              static_cast<uint32_t>(args[0]));
  };
  if (shorty == "IF") {
    using fntype = jint(JNIEnv*, jclass, jfloat);
    auto* fn = reinterpret_cast<fntype*>(jni_code);
    ScopedObjectAccessUnchecked soa2(self);
    ScopedLocalRef<jclass> klass(soa2.Env(),
                                 soa2.AddLocalReference<jclass>(method->GetDeclaringClass()));
    jfloat farg;
    uint32_t bits = args[0];
    __builtin_memcpy(&farg, &bits, sizeof(farg));
    ScopedThreadStateChange tsc(self, ThreadState::kNative);
    result->SetI(fn(soa2.Env(), klass.get(), farg));
    return true;
  }
  if (shorty == "FI") {
    using fntype = jfloat(JNIEnv*, jclass, jint);
    auto* fn = reinterpret_cast<fntype*>(jni_code);
    ScopedObjectAccessUnchecked soa2(self);
    ScopedLocalRef<jclass> klass(soa2.Env(),
                                 soa2.AddLocalReference<jclass>(method->GetDeclaringClass()));
    ScopedThreadStateChange tsc(self, ThreadState::kNative);
    result->SetF(fn(soa2.Env(), klass.get(), static_cast<jint>(args[0])));
    return true;
  }
  if (shorty == "FJ") {
    // NativeConverter.getAveBytesPerChar / getAveCharsPerByte
    using fntype = jfloat(JNIEnv*, jclass, jlong);
    auto* fn = reinterpret_cast<fntype*>(jni_code);
    ScopedObjectAccessUnchecked soa2(self);
    ScopedLocalRef<jclass> klass(soa2.Env(),
                                 soa2.AddLocalReference<jclass>(method->GetDeclaringClass()));
    ScopedThreadStateChange tsc(self, ThreadState::kNative);
    result->SetF(fn(soa2.Env(), klass.get(), jlong_arg0()));
    return true;
  }
  if (shorty == "IJ") {
    // NativeConverter.getMaxBytesPerChar
    using fntype = jint(JNIEnv*, jclass, jlong);
    auto* fn = reinterpret_cast<fntype*>(jni_code);
    ScopedObjectAccessUnchecked soa2(self);
    ScopedLocalRef<jclass> klass(soa2.Env(),
                                 soa2.AddLocalReference<jclass>(method->GetDeclaringClass()));
    ScopedThreadStateChange tsc(self, ThreadState::kNative);
    result->SetI(fn(soa2.Env(), klass.get(), jlong_arg0()));
    return true;
  }
  if (shorty == "VJ") {
    // closeConverter / reset*
    using fntype = void(JNIEnv*, jclass, jlong);
    auto* fn = reinterpret_cast<fntype*>(jni_code);
    ScopedObjectAccessUnchecked soa2(self);
    ScopedLocalRef<jclass> klass(soa2.Env(),
                                 soa2.AddLocalReference<jclass>(method->GetDeclaringClass()));
    ScopedThreadStateChange tsc(self, ThreadState::kNative);
    fn(soa2.Env(), klass.get(), jlong_arg0());
    return true;
  }
  if (shorty == "JL") {
    // openConverter(String)
    using fntype = jlong(JNIEnv*, jclass, jstring);
    auto* fn = reinterpret_cast<fntype*>(jni_code);
    ScopedObjectAccessUnchecked soa2(self);
    ScopedLocalRef<jclass> klass(soa2.Env(),
                                 soa2.AddLocalReference<jclass>(method->GetDeclaringClass()));
    ScopedLocalRef<jobject> arg0(soa2.Env(),
                                 soa2.AddLocalReference<jobject>(
                                     reinterpret_cast<StackReference<mirror::Object>*>(&args[0])
                                         ->AsMirrorPtr()));
    ScopedThreadStateChange tsc(self, ThreadState::kNative);
    result->SetJ(fn(soa2.Env(), klass.get(), reinterpret_cast<jstring>(arg0.get())));
    return true;
  }
  if (shorty == "LJ") {
    // getSubstitutionBytes(long)
    using fntype = jbyteArray(JNIEnv*, jclass, jlong);
    auto* fn = reinterpret_cast<fntype*>(jni_code);
    ScopedObjectAccessUnchecked soa2(self);
    ScopedLocalRef<jclass> klass(soa2.Env(),
                                 soa2.AddLocalReference<jclass>(method->GetDeclaringClass()));
    jbyteArray jresult;
    {
      ScopedThreadStateChange tsc(self, ThreadState::kNative);
      jresult = fn(soa2.Env(), klass.get(), jlong_arg0());
    }
    result->SetL(soa2.Decode<mirror::Object>(jresult));
    return true;
  }
  if (shorty == "VLJ") {
    // registerConverter(Object, long) — Object in args[0], long in args[1..2]
    using fntype = void(JNIEnv*, jclass, jobject, jlong);
    auto* fn = reinterpret_cast<fntype*>(jni_code);
    ScopedObjectAccessUnchecked soa2(self);
    ScopedLocalRef<jclass> klass(soa2.Env(),
                                 soa2.AddLocalReference<jclass>(method->GetDeclaringClass()));
    ScopedLocalRef<jobject> arg0(soa2.Env(),
                                 soa2.AddLocalReference<jobject>(
                                     reinterpret_cast<StackReference<mirror::Object>*>(&args[0])
                                         ->AsMirrorPtr()));
    jlong jarg = (static_cast<uint64_t>(args[2]) << 32) | static_cast<uint32_t>(args[1]);
    ScopedThreadStateChange tsc(self, ThreadState::kNative);
    fn(soa2.Env(), klass.get(), arg0.get(), jarg);
    return true;
  }
  if (shorty == "VJL") {
    // (long, Object)
    using fntype = void(JNIEnv*, jclass, jlong, jobject);
    auto* fn = reinterpret_cast<fntype*>(jni_code);
    ScopedObjectAccessUnchecked soa2(self);
    ScopedLocalRef<jclass> klass(soa2.Env(),
                                 soa2.AddLocalReference<jclass>(method->GetDeclaringClass()));
    ScopedLocalRef<jobject> arg1(soa2.Env(),
                                 soa2.AddLocalReference<jobject>(
                                     reinterpret_cast<StackReference<mirror::Object>*>(&args[2])
                                         ->AsMirrorPtr()));
    ScopedThreadStateChange tsc(self, ThreadState::kNative);
    fn(soa2.Env(), klass.get(), jlong_arg0(), arg1.get());
    return true;
  }
  if (shorty == "VJIIL") {
    // setCallbackDecode/Encode(long, int, int, Object)
    using fntype = void(JNIEnv*, jclass, jlong, jint, jint, jobject);
    auto* fn = reinterpret_cast<fntype*>(jni_code);
    ScopedObjectAccessUnchecked soa2(self);
    ScopedLocalRef<jclass> klass(soa2.Env(),
                                 soa2.AddLocalReference<jclass>(method->GetDeclaringClass()));
    ScopedLocalRef<jobject> arg3(soa2.Env(),
                                 soa2.AddLocalReference<jobject>(
                                     reinterpret_cast<StackReference<mirror::Object>*>(&args[4])
                                         ->AsMirrorPtr()));
    ScopedThreadStateChange tsc(self, ThreadState::kNative);
    fn(soa2.Env(),
       klass.get(),
       jlong_arg0(),
       static_cast<jint>(args[2]),
       static_cast<jint>(args[3]),
       arg3.get());
    return true;
  }
  if (shorty == "IJLILILZ") {
    // NativeConverter.encode / decode
    using fntype = jint(JNIEnv*, jclass, jlong, jobject, jint, jobject, jint, jintArray, jboolean);
    auto* fn = reinterpret_cast<fntype*>(jni_code);
    ScopedObjectAccessUnchecked soa2(self);
    ScopedLocalRef<jclass> klass(soa2.Env(),
                                 soa2.AddLocalReference<jclass>(method->GetDeclaringClass()));
    // args layout: J@0, L@2, I@3, L@4, I@5, L@6, Z@7
    ScopedLocalRef<jobject> src(soa2.Env(),
                                soa2.AddLocalReference<jobject>(
                                    reinterpret_cast<StackReference<mirror::Object>*>(&args[2])
                                        ->AsMirrorPtr()));
    ScopedLocalRef<jobject> tgt(soa2.Env(),
                                soa2.AddLocalReference<jobject>(
                                    reinterpret_cast<StackReference<mirror::Object>*>(&args[4])
                                        ->AsMirrorPtr()));
    ScopedLocalRef<jobject> data(soa2.Env(),
                                 soa2.AddLocalReference<jobject>(
                                     reinterpret_cast<StackReference<mirror::Object>*>(&args[6])
                                         ->AsMirrorPtr()));
    ScopedThreadStateChange tsc(self, ThreadState::kNative);
    result->SetI(fn(soa2.Env(),
                    klass.get(),
                    jlong_arg0(),
                    src.get(),
                    static_cast<jint>(args[3]),
                    tgt.get(),
                    static_cast<jint>(args[5]),
                    reinterpret_cast<jintArray>(data.get()),
                    static_cast<jboolean>(args[7])));
    return true;
  }
  if (shorty == "JD") {
    using fntype = jlong(JNIEnv*, jclass, jdouble);
    auto* fn = reinterpret_cast<fntype*>(jni_code);
    ScopedObjectAccessUnchecked soa2(self);
    ScopedLocalRef<jclass> klass(soa2.Env(),
                                 soa2.AddLocalReference<jclass>(method->GetDeclaringClass()));
    jdouble darg;
    uint64_t bits = (static_cast<uint64_t>(args[1]) << 32) | static_cast<uint32_t>(args[0]);
    __builtin_memcpy(&darg, &bits, sizeof(darg));
    ScopedThreadStateChange tsc(self, ThreadState::kNative);
    result->SetJ(fn(soa2.Env(), klass.get(), darg));
    return true;
  }
  if (shorty == "DJ") {
    using fntype = jdouble(JNIEnv*, jclass, jlong);
    auto* fn = reinterpret_cast<fntype*>(jni_code);
    ScopedObjectAccessUnchecked soa2(self);
    ScopedLocalRef<jclass> klass(soa2.Env(),
                                 soa2.AddLocalReference<jclass>(method->GetDeclaringClass()));
    jlong jarg = (static_cast<uint64_t>(args[1]) << 32) | static_cast<uint32_t>(args[0]);
    ScopedThreadStateChange tsc(self, ThreadState::kNative);
    result->SetD(fn(soa2.Env(), klass.get(), jarg));
    return true;
  }
  for (char c : shorty) {
    if (c == 'F' || c == 'D') {
      return false;
    }
  }

  ScopedObjectAccessUnchecked soa(self);
  JNIEnv* env = soa.Env();
  // Keep local refs alive for the duration of the native call.
  std::vector<ScopedLocalRef<jobject>> local_refs;
  local_refs.reserve(8);
  auto add_local = [&](ObjPtr<mirror::Object> o) -> jobject {
    local_refs.emplace_back(env, soa.AddLocalReference<jobject>(o));
    return local_refs.back().get();
  };

  uint64_t slots[8] = {};
  size_t nslots = 0;
  auto push = [&](uint64_t v) {
    CHECK_LT(nslots, 8u) << method->PrettyMethod() << " shorty=" << shorty;
    slots[nslots++] = v;
  };

  push(reinterpret_cast<uint64_t>(env));
  if (method->IsStatic()) {
    push(reinterpret_cast<uint64_t>(add_local(method->GetDeclaringClass())));
  } else {
    CHECK(receiver != nullptr);
    push(reinterpret_cast<uint64_t>(add_local(receiver)));
  }

  // shorty[0] is return type; args follow.
  size_t arg_pos = 0;
  for (size_t i = 1; i < shorty.size(); ++i) {
    switch (shorty[i]) {
      case 'Z':
      case 'B':
      case 'C':
      case 'S':
      case 'I':
      case 'F':  // rejected above
        push(static_cast<uint64_t>(static_cast<uint32_t>(args[arg_pos])));
        arg_pos += 1;
        break;
      case 'J':
      case 'D': {  // rejected above for D; J is wide
        uint64_t wide = (static_cast<uint64_t>(args[arg_pos + 1]) << 32) |
                        static_cast<uint32_t>(args[arg_pos]);
        push(wide);
        arg_pos += 2;
        break;
      }
      case 'L': {
        ObjPtr<mirror::Object> o =
            reinterpret_cast<StackReference<mirror::Object>*>(&args[arg_pos])->AsMirrorPtr();
        push(reinterpret_cast<uint64_t>(o == nullptr ? nullptr : add_local(o)));
        arg_pos += 1;
        break;
      }
      default:
        return false;
    }
  }

  using jni_fn8 = uint64_t (*)(uint64_t, uint64_t, uint64_t, uint64_t,
                               uint64_t, uint64_t, uint64_t, uint64_t);
  auto* fn = reinterpret_cast<jni_fn8>(jni_code);
  uint64_t raw;
  {
    ScopedThreadStateChange tsc(self, ThreadState::kNative);
    raw = fn(slots[0], slots[1], slots[2], slots[3], slots[4], slots[5], slots[6], slots[7]);
  }

  switch (shorty[0]) {
    case 'V':
      break;
    case 'Z':
      result->SetZ(static_cast<uint8_t>(raw));
      break;
    case 'B':
      result->SetB(static_cast<int8_t>(raw));
      break;
    case 'C':
      result->SetC(static_cast<uint16_t>(raw));
      break;
    case 'S':
      result->SetS(static_cast<int16_t>(raw));
      break;
    case 'I':
      result->SetI(static_cast<int32_t>(raw));
      break;
    case 'J':
      result->SetJ(static_cast<int64_t>(raw));
      break;
    case 'L':
      result->SetL(soa.Decode<mirror::Object>(reinterpret_cast<jobject>(raw)));
      break;
    default:
      return false;
  }
  return true;
}

```
