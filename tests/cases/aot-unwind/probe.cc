#include <windows.h>

#include <jni.h>

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <utility>
#include <vector>

#include "art_method-inl.h"
#include "oat/oat.h"
#include "scoped_thread_state_change-inl.h"

namespace {

struct UnwindOperation {
  uint8_t code_offset;
  uint8_t operation;
  uint8_t info;
  uint32_t value;
};

jboolean Fail(JNIEnv* env, const char* message) {
  std::cerr << "W031_AOT_UNWIND_FAIL: " << message << '\n';
  jclass exception = env->FindClass("java/lang/AssertionError");
  if (exception != nullptr) {
    env->ThrowNew(exception, message);
  }
  return JNI_FALSE;
}

uint16_t Load16(const uint8_t* data) {
  return static_cast<uint16_t>(data[0]) | (static_cast<uint16_t>(data[1]) << 8u);
}

uint32_t Load32(const uint8_t* data) {
  return static_cast<uint32_t>(Load16(data)) |
         (static_cast<uint32_t>(Load16(data + 2u)) << 16u);
}

uint64_t* ContextGpr(CONTEXT* context, uint8_t reg) {
  switch (reg) {
    case 3u: return &context->Rbx;
    case 5u: return &context->Rbp;
    case 6u: return &context->Rsi;
    case 7u: return &context->Rdi;
    case 12u: return &context->R12;
    case 13u: return &context->R13;
    case 14u: return &context->R14;
    case 15u: return &context->R15;
    default: return nullptr;
  }
}

M128A* ContextXmm(CONTEXT* context, uint8_t reg) {
  switch (reg) {
    case 6u: return &context->Xmm6;
    case 7u: return &context->Xmm7;
    case 8u: return &context->Xmm8;
    case 9u: return &context->Xmm9;
    case 10u: return &context->Xmm10;
    case 11u: return &context->Xmm11;
    case 12u: return &context->Xmm12;
    case 13u: return &context->Xmm13;
    case 14u: return &context->Xmm14;
    case 15u: return &context->Xmm15;
    default: return nullptr;
  }
}

bool DecodeUnwindInfo(DWORD64 image_base,
                      const RUNTIME_FUNCTION& function,
                      std::vector<UnwindOperation>* operations,
                      uint8_t* prologue_size,
                      uint8_t* frame_register,
                      uint8_t* frame_offset) {
  const uint8_t* data = reinterpret_cast<const uint8_t*>(image_base + function.UnwindData);
  if (data[0] != 1u) {
    return false;
  }
  *prologue_size = data[1];
  const uint8_t slot_count = data[2];
  *frame_register = data[3] & 0x0fu;
  *frame_offset = data[3] >> 4u;
  size_t slot = 0u;
  while (slot < slot_count) {
    UnwindOperation decoded = {data[4u + slot * 2u],
                               static_cast<uint8_t>(data[5u + slot * 2u] & 0x0fu),
                               static_cast<uint8_t>(data[5u + slot * 2u] >> 4u),
                               0u};
    size_t used_slots = 1u;
    switch (decoded.operation) {
      case 0u:
      case 3u:
        break;
      case 1u:
        if (decoded.info == 0u) {
          used_slots = 2u;
          decoded.value = static_cast<uint32_t>(Load16(data + 6u + slot * 2u)) * 8u;
        } else if (decoded.info == 1u) {
          used_slots = 3u;
          decoded.value = Load32(data + 6u + slot * 2u);
        } else {
          return false;
        }
        break;
      case 2u:
        decoded.value = static_cast<uint32_t>(decoded.info) * 8u + 8u;
        break;
      case 8u:
        used_slots = 2u;
        decoded.value = static_cast<uint32_t>(Load16(data + 6u + slot * 2u)) * 16u;
        break;
      case 9u:
        used_slots = 3u;
        decoded.value = Load32(data + 6u + slot * 2u);
        break;
      default:
        return false;
    }
    if (used_slots > static_cast<size_t>(slot_count) - slot) {
      return false;
    }
    operations->push_back(decoded);
    slot += used_slots;
  }
  std::sort(operations->begin(), operations->end(), [](const auto& lhs, const auto& rhs) {
    return lhs.code_offset < rhs.code_offset;
  });
  return true;
}

bool SyntheticVirtualUnwind(DWORD64 image_base, const RUNTIME_FUNCTION& function) {
  std::vector<UnwindOperation> operations;
  uint8_t prologue_size = 0u;
  uint8_t frame_register = 0u;
  uint8_t frame_offset = 0u;
  if (!DecodeUnwindInfo(image_base,
                        function,
                        &operations,
                        &prologue_size,
                        &frame_register,
                        &frame_offset) ||
      frame_register != 5u || prologue_size == 0u ||
      function.BeginAddress + prologue_size >= function.EndAddress) {
    return false;
  }

  size_t frame_bytes = 0u;
  for (const UnwindOperation& operation : operations) {
    if (operation.operation == 0u) {
      frame_bytes += sizeof(uint64_t);
    } else if (operation.operation == 1u || operation.operation == 2u) {
      frame_bytes += operation.value;
    }
  }
  if (frame_bytes == 0u || frame_bytes > 512u * 1024u) {
    return false;
  }

  std::vector<uint8_t> stack(frame_bytes + 8192u, 0u);
  const uintptr_t stack_begin = reinterpret_cast<uintptr_t>(stack.data());
  const uintptr_t stack_end = stack_begin + stack.size();
  const uintptr_t entry_rsp = ((stack_end - 4096u) & ~uintptr_t{15u}) + 8u;
  constexpr uint64_t kReturnAddress = UINT64_C(0x123456789abcdef0);
  *reinterpret_cast<uint64_t*>(entry_rsp) = kReturnAddress;

  CONTEXT context = {};
  context.ContextFlags = CONTEXT_CONTROL | CONTEXT_INTEGER | CONTEXT_FLOATING_POINT;
  std::vector<std::pair<uint8_t, uint64_t>> expected_gprs;
  std::vector<std::pair<uint8_t, M128A>> expected_xmms;
  uintptr_t rsp = entry_rsp;
  for (const UnwindOperation& operation : operations) {
    switch (operation.operation) {
      case 0u: {
        uint64_t* reg = ContextGpr(&context, operation.info);
        if (reg == nullptr || rsp < stack_begin + sizeof(uint64_t)) {
          return false;
        }
        rsp -= sizeof(uint64_t);
        const uint64_t saved = UINT64_C(0x1100000000000000) + operation.info;
        *reinterpret_cast<uint64_t*>(rsp) = saved;
        *reg = UINT64_C(0x2200000000000000) + operation.info;
        expected_gprs.emplace_back(operation.info, saved);
        break;
      }
      case 1u:
      case 2u:
        if (operation.value > rsp - stack_begin) {
          return false;
        }
        rsp -= operation.value;
        break;
      case 3u: {
        uint64_t* reg = ContextGpr(&context, frame_register);
        if (reg == nullptr) {
          return false;
        }
        *reg = rsp + static_cast<uintptr_t>(frame_offset) * 16u;
        break;
      }
      case 8u:
      case 9u: {
        M128A* reg = ContextXmm(&context, operation.info);
        if (reg == nullptr || operation.value > stack_end - rsp - sizeof(M128A)) {
          return false;
        }
        M128A saved = {UINT64_C(0x3300000000000000) + operation.info,
                       static_cast<int64_t>(UINT64_C(0x4400000000000000) + operation.info)};
        std::memcpy(reinterpret_cast<void*>(rsp + operation.value), &saved, sizeof(saved));
        reg->Low = 0u;
        reg->High = 0;
        expected_xmms.emplace_back(operation.info, saved);
        break;
      }
      default:
        return false;
    }
  }

  context.Rsp = rsp;
  context.Rip = image_base + function.BeginAddress + prologue_size;
  PVOID handler_data = nullptr;
  DWORD64 establisher_frame = 0u;
  RtlVirtualUnwind(UNW_FLAG_NHANDLER,
                   image_base,
                   context.Rip,
                   const_cast<RUNTIME_FUNCTION*>(&function),
                   &context,
                   &handler_data,
                   &establisher_frame,
                   nullptr);
  if (context.Rip != kReturnAddress || context.Rsp != entry_rsp + sizeof(uint64_t)) {
    return false;
  }
  for (const auto& [reg, expected] : expected_gprs) {
    if (*ContextGpr(&context, reg) != expected) {
      return false;
    }
  }
  for (const auto& [reg, expected] : expected_xmms) {
    M128A* actual = ContextXmm(&context, reg);
    if (actual->Low != expected.Low || actual->High != expected.High) {
      return false;
    }
  }
  return true;
}

bool IsTrampoline(const art::OatHeader& header, const void* entry) {
  for (uint32_t raw = 0u; raw <= static_cast<uint32_t>(art::StubType::kLast); ++raw) {
    if (entry == header.GetOatAddress(static_cast<art::StubType>(raw))) {
      return true;
    }
  }
  return false;
}

}  // namespace

extern "C" __declspec(dllexport) jboolean JNICALL
Java_W031AotUnwindProbe_nativeAudit(JNIEnv* env,
                                    jclass,
                                    jobjectArray managed_methods,
                                    jobjectArray native_methods) {
  art::ScopedObjectAccess soa(env);
  const art::OatHeader* oat_header = nullptr;
  DWORD64 oat_base = 0u;
  RUNTIME_FUNCTION managed_function = {};
  size_t managed_candidates = 0u;
  for (jsize index = 0; index < env->GetArrayLength(managed_methods); ++index) {
    jobject reflected = env->GetObjectArrayElement(managed_methods, index);
    art::ArtMethod* method = art::ArtMethod::FromReflectedMethod(soa, reflected);
    env->DeleteLocalRef(reflected);
    if (method == nullptr || method->IsNative()) {
      continue;
    }
    ++managed_candidates;
    // Runtime startup may replace the dispatch entrypoint with nterp. Inspect
    // the method's underlying boot-OAT code instead of its current dispatcher.
    const void* entry = method->GetOatMethodQuickCode(art::kRuntimePointerSize);
    DWORD64 image_base = 0u;
    PRUNTIME_FUNCTION function =
        RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(entry), &image_base, nullptr);
    const art::OatHeader* candidate = reinterpret_cast<const art::OatHeader*>(image_base);
    if (function != nullptr && candidate->IsValid() && !IsTrampoline(*candidate, entry) &&
        (reinterpret_cast<const uint8_t*>(image_base + function->UnwindData)[3] & 0x0fu) == 5u) {
      oat_header = candidate;
      oat_base = image_base;
      managed_function = *function;
      break;
    }
  }
  if (oat_header == nullptr || oat_base == 0u) {
    return Fail(env, "no RBP-anchored managed boot-OAT method was found");
  }
  if (!SyntheticVirtualUnwind(oat_base, managed_function)) {
    return Fail(env, "RtlVirtualUnwind failed for managed boot-OAT metadata");
  }

  size_t jni_candidates = 0u;
  bool found_jni = false;
  for (jsize index = 0; index < env->GetArrayLength(native_methods); ++index) {
    jobject reflected = env->GetObjectArrayElement(native_methods, index);
    art::ArtMethod* method = art::ArtMethod::FromReflectedMethod(soa, reflected);
    env->DeleteLocalRef(reflected);
    if (method == nullptr || !method->IsNative()) {
      continue;
    }
    ++jni_candidates;
    const void* entry = method->GetOatMethodQuickCode(art::kRuntimePointerSize);
    DWORD64 image_base = 0u;
    PRUNTIME_FUNCTION function =
        RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(entry), &image_base, nullptr);
    if (function != nullptr && image_base == oat_base && !IsTrampoline(*oat_header, entry)) {
      found_jni = true;
      break;
    }
  }
  if (!found_jni) {
    return Fail(env, "no compiled JNI boot-OAT method was found");
  }

  size_t trampolines = 0u;
  for (uint32_t raw = 0u; raw <= static_cast<uint32_t>(art::StubType::kLast); ++raw) {
    const uint8_t* entry = oat_header->GetOatAddress(static_cast<art::StubType>(raw));
    DWORD64 image_base = 0u;
    PRUNTIME_FUNCTION function =
        RtlLookupFunctionEntry(reinterpret_cast<DWORD64>(entry), &image_base, nullptr);
    if (function == nullptr || image_base != oat_base ||
        function->BeginAddress != reinterpret_cast<DWORD64>(entry) - oat_base) {
      return Fail(env, "boot-OAT trampoline lookup did not match its registered range");
    }
    ++trampolines;
  }

  std::cout << "W031_AOT_UNWIND_PASS managed_candidates=" << managed_candidates
            << " jni_candidates=" << jni_candidates << " trampolines=" << trampolines
            << " virtual_unwind=pass\n";
  return JNI_TRUE;
}
