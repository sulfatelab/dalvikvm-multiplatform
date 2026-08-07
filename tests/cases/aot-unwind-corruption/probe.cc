#include <windows.h>

#include <jni.h>

#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <string>
#include <unordered_set>
#include <vector>

#include "gc/heap.h"
#include "oat/oat_file.h"
#include "runtime.h"

namespace {

constexpr size_t kCaseCount = 23u;

jboolean Fail(JNIEnv *env, const std::string &message) {
  std::cerr << "W039_UNWIND_CORRUPTION_FAIL: " << message << '\n';
  jclass exception = env->FindClass("java/lang/AssertionError");
  if (exception != nullptr) {
    env->ThrowNew(exception, message.c_str());
  }
  return JNI_FALSE;
}

bool HasUnwindDiagnostic(const std::string &message) {
  return message.find("Windows OAT unwind") != std::string::npos ||
         message.find(".oat_unwind.windows") != std::string::npos ||
         message.find("oatunwindwindows") != std::string::npos;
}

std::unique_ptr<art::OatFile> OpenOat(const std::filesystem::path &path,
                                      bool executable,
                                      std::string *error_message) {
  return std::unique_ptr<art::OatFile>(art::OatFile::Open(
      /*zip_fd=*/-1, path.string(), path.string(), executable,
      /*low_4gb=*/false, error_message));
}

bool ReadCases(const std::filesystem::path &root,
               std::vector<std::string> *cases, std::string *error_message) {
  std::ifstream stream(root / "cases.txt");
  if (!stream) {
    *error_message = "cannot read the unwind corruption case list";
    return false;
  }
  std::unordered_set<std::string> unique;
  std::string name;
  while (std::getline(stream, name)) {
    if (!name.empty() && name.back() == '\r') {
      name.pop_back();
    }
    if (name.empty() ||
        name.find_first_not_of("abcdefghijklmnopqrstuvwxyz-0123456789") !=
            std::string::npos ||
        !unique.insert(name).second) {
      *error_message = "unwind corruption case list is malformed";
      return false;
    }
    cases->push_back(name);
  }
  if (!stream.eof() || cases->size() != kCaseCount) {
    *error_message = "unwind corruption case list must contain 23 cases";
    return false;
  }
  return true;
}

bool ReadFirstEntryOffset(const std::filesystem::path &root,
                          uint32_t *first_entry_offset,
                          std::string *error_message) {
  std::ifstream stream(root / "first-entry.txt");
  uint64_t value = 0u;
  if (!(stream >> value) || value == 0u || value > UINT32_MAX) {
    *error_message = "first unwind entry offset is invalid";
    return false;
  }
  stream >> std::ws;
  if (!stream.eof()) {
    *error_message = "first unwind entry record has trailing data";
    return false;
  }
  *first_entry_offset = static_cast<uint32_t>(value);
  return true;
}

bool CheckCanonicalOpen(const std::filesystem::path &path, bool executable,
                        uint32_t first_entry_offset,
                        std::string *error_message) {
  std::unique_ptr<art::OatFile> oat_file =
      OpenOat(path, executable, error_message);
  if (oat_file == nullptr) {
    *error_message = "canonical unwind OAT open failed: " + *error_message;
    return false;
  }
  if (!executable) {
    return true;
  }

  const DWORD64 image_base = reinterpret_cast<DWORD64>(oat_file->Begin());
  const DWORD64 pc = image_base + first_entry_offset;
  DWORD64 lookup_base = 0u;
  PRUNTIME_FUNCTION function =
      RtlLookupFunctionEntry(pc, &lookup_base, nullptr);
  if (function == nullptr || lookup_base != image_base ||
      function->BeginAddress != first_entry_offset) {
    *error_message =
        "canonical executable open did not register its first unwind entry";
    return false;
  }
  oat_file.reset();
  lookup_base = 0u;
  if (RtlLookupFunctionEntry(pc, &lookup_base, nullptr) != nullptr) {
    *error_message = "canonical executable close left a stale unwind entry";
    return false;
  }
  return true;
}

} // namespace

extern "C" __declspec(dllexport) jboolean JNICALL
Java_W039BootOatUnwindCorruptionProbe_nativeAudit(JNIEnv *env, jclass) {
  const char *root_value = std::getenv("W039_UNWIND_CORRUPTION_ROOT");
  if (root_value == nullptr || root_value[0] == '\0') {
    return Fail(env, "W039_UNWIND_CORRUPTION_ROOT is missing");
  }
  const std::filesystem::path root(root_value);
  std::vector<std::string> cases;
  std::string error_message;
  uint32_t first_entry_offset = 0u;
  if (!ReadCases(root, &cases, &error_message) ||
      !ReadFirstEntryOffset(root, &first_entry_offset, &error_message)) {
    return Fail(env, error_message);
  }

  for (size_t pass = 0u; pass != 2u; ++pass) {
    if (!CheckCanonicalOpen(root / "canonical.oat", false, first_entry_offset,
                            &error_message) ||
        !CheckCanonicalOpen(root / "canonical.oat", true, first_entry_offset,
                            &error_message)) {
      return Fail(env, error_message);
    }
    if (pass == 0u) {
      for (const std::string &case_name : cases) {
        for (bool executable : {false, true}) {
          error_message.clear();
          if (OpenOat(root / (case_name + ".oat"), executable,
                      &error_message) != nullptr) {
            return Fail(env, "corrupt unwind OAT was accepted: " + case_name);
          }
          if (!HasUnwindDiagnostic(error_message)) {
            return Fail(env,
                        "corrupt unwind OAT has an unrelated diagnostic: " +
                            case_name + ": " + error_message);
          }
        }
      }
    }
  }

  std::cout << "W039_UNWIND_CORRUPTION_PASS cases=23 opens=50 "
               "validation_only=25 executable=25 lifecycle=clean\n";
  return JNI_TRUE;
}

extern "C" __declspec(dllexport) jboolean JNICALL
Java_W039BootOatUnwindFallbackProbe_nativeVerifyImageless(JNIEnv *env, jclass) {
  const char *case_name = std::getenv("W039_UNWIND_FALLBACK_CASE");
  if (case_name == nullptr || case_name[0] == '\0' ||
      std::string(case_name).find_first_not_of(
          "abcdefghijklmnopqrstuvwxyz-0123456789") != std::string::npos) {
    return Fail(env, "W039_UNWIND_FALLBACK_CASE is invalid");
  }
  art::Runtime *runtime = art::Runtime::Current();
  if (runtime == nullptr || runtime->GetHeap() == nullptr ||
      !runtime->GetHeap()->GetBootImageSpaces().empty()) {
    return Fail(env, "corrupt unwind fallback retained a boot image space");
  }
  std::cout << "W039_UNWIND_FALLBACK_PASS case=" << case_name
            << " image_spaces=0\n";
  return JNI_TRUE;
}
