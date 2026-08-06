#include <fcntl.h>
#include <io.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "base/mem_map.h"

namespace {

bool Check(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "W030_PRIVATE_COPY_FAIL: %s\n", message);
  }
  return condition;
}

bool HasProtection(void* address, DWORD expected) {
  MEMORY_BASIC_INFORMATION info = {};
  return ::VirtualQuery(address, &info, sizeof(info)) == sizeof(info) && info.State == MEM_COMMIT &&
         (info.Protect & 0xffu) == expected;
}

int CreateInputFile(const std::vector<uint8_t>& contents, std::wstring* path) {
  wchar_t temporary_directory[MAX_PATH] = {};
  wchar_t temporary_name[MAX_PATH] = {};
  if (::GetTempPathW(MAX_PATH, temporary_directory) == 0u ||
      ::GetTempFileNameW(temporary_directory, L"oat", 0u, temporary_name) == 0u) {
    return -1;
  }
  int fd =
      _wopen(temporary_name, _O_BINARY | _O_RDWR | _O_TRUNC | _O_NOINHERIT, _S_IREAD | _S_IWRITE);
  if (fd < 0) {
    ::DeleteFileW(temporary_name);
    return -1;
  }
  size_t written = 0u;
  while (written != contents.size()) {
    int result =
        _write(fd, contents.data() + written, static_cast<unsigned int>(contents.size() - written));
    if (result <= 0) {
      _close(fd);
      ::DeleteFileW(temporary_name);
      return -1;
    }
    written += static_cast<size_t>(result);
  }
  *path = temporary_name;
  return fd;
}

}  // namespace

int main() {
  art::MemMap::Init();
  bool ok = true;
  std::string error;

  SYSTEM_INFO system_info = {};
  ::GetSystemInfo(&system_info);
  ok &=
      Check(system_info.dwPageSize == 4u * 1024u, "initial profile requires a 4-KiB Windows page");
  ok &= Check(system_info.dwAllocationGranularity == 64u * 1024u,
              "initial profile requires 64-KiB Windows allocation granularity");
  ok &= Check(art::MemMap::GetPageSize() == system_info.dwPageSize,
              "ART and Windows page sizes disagree");

  const size_t page_size = art::MemMap::GetPageSize();
  constexpr size_t kSourceOffset = 37u;
  std::vector<uint8_t> contents(3u * page_size + kSourceOffset);
  for (size_t i = 0u; i < contents.size(); ++i) {
    contents[i] = static_cast<uint8_t>((i * 29u + 11u) & 0xffu);
  }
  std::wstring input_path;
  int fd = CreateInputFile(contents, &input_path);
  ok &= Check(fd >= 0, "failed to create the private-copy input file");

  if (fd >= 0) {
    error.clear();
    void* section = art::MemMap::CreatePageFileSection(page_size, &error);
    ok &= Check(section != nullptr, error.c_str());
    art::MemMap section_view = art::MemMap::MapFileSection(section,
                                                           page_size,
                                                           PROT_READ | PROT_WRITE,
                                                           /*low_4gb=*/false,
                                                           /*start_offset=*/0u,
                                                           "w030-section-view-control",
                                                           &error);
    ok &= Check(section_view.IsValid(), error.c_str());
    error.clear();
    art::MemMap section_copy = art::MemMap::MapFileAtAddressPrivateCopy(
        section_view.IsValid() ? section_view.Begin() : nullptr,
        page_size,
        PROT_READ,
        fd,
        static_cast<off_t>(kSourceOffset),
        "w030-private-copy-input",
        &error);
    ok &= Check(!section_copy.IsValid(), "section-view private copy unexpectedly succeeded");
    ok &= Check(error.find("not one private allocation") != std::string::npos,
                "section-view private copy returned the wrong diagnostic");
    section_view.Reset();
    if (section != nullptr) {
      ok &= Check(::CloseHandle(static_cast<HANDLE>(section)) != FALSE,
                  "failed to close the section-view control handle");
    }

    void* foreign = ::VirtualAlloc(nullptr, page_size, MEM_RESERVE | MEM_COMMIT, PAGE_NOACCESS);
    ok &= Check(foreign != nullptr, "failed to create the foreign control allocation");
    error.clear();
    art::MemMap foreign_copy =
        art::MemMap::MapFileAtAddressPrivateCopy(reinterpret_cast<uint8_t*>(foreign),
                                                 page_size,
                                                 PROT_READ,
                                                 fd,
                                                 static_cast<off_t>(kSourceOffset),
                                                 "w030-private-copy-input",
                                                 &error);
    ok &= Check(!foreign_copy.IsValid(), "foreign private-copy destination unexpectedly succeeded");
    ok &= Check(error.find("not ART-owned") != std::string::npos,
                "foreign private-copy destination returned the wrong diagnostic");
    ok &= Check(foreign == nullptr || HasProtection(foreign, PAGE_NOACCESS),
                "rejected foreign copy changed destination protection");
    if (foreign != nullptr) {
      ok &= Check(::VirtualFree(foreign, 0u, MEM_RELEASE) != FALSE,
                  "failed to release the foreign control allocation");
    }

    error.clear();
    art::MemMap owner = art::MemMap::MapAnonymous(
        "w030-private-copy-owner", 4u * page_size, PROT_NONE, /*low_4gb=*/false, &error);
    ok &= Check(owner.IsValid(), error.c_str());
    void* allocation_base = owner.IsValid() ? owner.BaseBegin() : nullptr;

    error.clear();
    art::MemMap out_of_range = art::MemMap::MapFileAtAddressPrivateCopy(
        owner.IsValid() ? owner.Begin() : nullptr,
        page_size,
        PROT_READ,
        fd,
        static_cast<off_t>(contents.size() - page_size + 1u),
        "w030-private-copy-input",
        &error);
    ok &= Check(!out_of_range.IsValid(), "out-of-file private-copy range unexpectedly succeeded");
    ok &= Check(error.find("exceeds file") != std::string::npos,
                "out-of-file private-copy range returned the wrong diagnostic");
    ok &= Check(!owner.IsValid() || HasProtection(owner.Begin(), PAGE_NOACCESS),
                "rejected private copy changed destination protection");

    error.clear();
    art::MemMap unaligned =
        art::MemMap::MapFileAtAddressPrivateCopy(owner.IsValid() ? owner.Begin() + 1u : nullptr,
                                                 page_size,
                                                 PROT_READ,
                                                 fd,
                                                 static_cast<off_t>(kSourceOffset),
                                                 "w030-private-copy-input",
                                                 &error);
    ok &= Check(!unaligned.IsValid(), "unaligned private-copy destination unexpectedly succeeded");
    ok &= Check(error.find("unaligned") != std::string::npos,
                "unaligned private-copy destination returned the wrong diagnostic");

    uint8_t* read_address = owner.IsValid() ? owner.Begin() + page_size : nullptr;
    error.clear();
    art::MemMap read_copy =
        art::MemMap::MapFileAtAddressPrivateCopy(read_address,
                                                 page_size,
                                                 PROT_READ,
                                                 fd,
                                                 static_cast<off_t>(kSourceOffset),
                                                 "w030-private-copy-input",
                                                 &error);
    ok &= Check(read_copy.IsValid(), error.c_str());
    if (owner.IsValid() && read_copy.IsValid()) {
      ok &= Check(read_copy.Begin() == read_address, "private copy moved from its exact address");
      ok &= Check(std::memcmp(read_copy.Begin(), contents.data() + kSourceOffset, page_size) == 0,
                  "private copy bytes differ from the checked file range");
      ok &= Check(HasProtection(read_copy.Begin(), PAGE_READONLY),
                  "validation-only private copy is not R/NX");
      ok &= Check(HasProtection(owner.Begin(), PAGE_NOACCESS) &&
                      HasProtection(owner.Begin() + 2u * page_size, PAGE_NOACCESS),
                  "private copy changed an adjacent no-access gap");
      owner.Reset();
      ok &= Check(std::memcmp(read_copy.Begin(), contents.data() + kSourceOffset, page_size) == 0,
                  "private-copy slice did not retain its allocation owner");
      read_copy.Reset();
      MEMORY_BASIC_INFORMATION info = {};
      ok &= Check(::VirtualQuery(allocation_base, &info, sizeof(info)) == sizeof(info),
                  "VirtualQuery failed after releasing private-copy owner");
      ok &= Check(info.State == MEM_FREE, "private-copy allocation was not released exactly once");
    }

    error.clear();
    art::MemMap executable_owner = art::MemMap::MapAnonymous("w030-executable-owner",
                                                             page_size,
                                                             PROT_NONE,
                                                             /*low_4gb=*/false,
                                                             &error);
    ok &= Check(executable_owner.IsValid(), error.c_str());
    art::MemMap executable_copy = art::MemMap::MapFileAtAddressPrivateCopy(
        executable_owner.IsValid() ? executable_owner.Begin() : nullptr,
        page_size,
        PROT_READ | PROT_EXEC,
        fd,
        static_cast<off_t>(kSourceOffset),
        "w030-private-copy-input",
        &error);
    ok &= Check(executable_copy.IsValid(), error.c_str());
    ok &= Check(
        !executable_copy.IsValid() || HasProtection(executable_copy.Begin(), PAGE_EXECUTE_READ),
        "executable private copy is not RX");
    executable_copy.Reset();
    executable_owner.Reset();

    error.clear();
    art::MemMap writable_owner = art::MemMap::MapAnonymous(
        "w030-writable-owner", page_size, PROT_NONE, /*low_4gb=*/false, &error);
    ok &= Check(writable_owner.IsValid(), error.c_str());
    art::MemMap writable_copy = art::MemMap::MapFileAtAddressPrivateCopy(
        writable_owner.IsValid() ? writable_owner.Begin() : nullptr,
        page_size,
        PROT_READ | PROT_WRITE,
        fd,
        static_cast<off_t>(kSourceOffset),
        "w030-private-copy-input",
        &error);
    ok &= Check(writable_copy.IsValid(), error.c_str());
    if (writable_copy.IsValid()) {
      ok &= Check(HasProtection(writable_copy.Begin(), PAGE_READWRITE),
                  "VDEX-style private copy is not RW/NX");
      const uint8_t original = contents[kSourceOffset];
      writable_copy.Begin()[0] ^= 0xffu;
      error.clear();
      art::MemMap independent_owner = art::MemMap::MapAnonymous(
          "w030-independent-owner", page_size, PROT_NONE, /*low_4gb=*/false, &error);
      art::MemMap independent_copy = art::MemMap::MapFileAtAddressPrivateCopy(
          independent_owner.IsValid() ? independent_owner.Begin() : nullptr,
          page_size,
          PROT_READ,
          fd,
          static_cast<off_t>(kSourceOffset),
          "w030-private-copy-input",
          &error);
      ok &= Check(independent_copy.IsValid(), error.c_str());
      ok &= Check(!independent_copy.IsValid() || independent_copy.Begin()[0] == original,
                  "private-copy mutation changed the source file");
    }
    writable_copy.Reset();
    writable_owner.Reset();

    error.clear();
    art::MemMap zero_owner = art::MemMap::MapAnonymous("w030-zero-owner",
                                                       3u * page_size,
                                                       PROT_NONE,
                                                       /*low_4gb=*/false,
                                                       &error);
    ok &= Check(zero_owner.IsValid(), error.c_str());
    art::MemMap zero_tail =
        art::MemMap::MapAnonymous("w030-zero-tail",
                                  zero_owner.IsValid() ? zero_owner.Begin() + page_size : nullptr,
                                  page_size,
                                  PROT_READ,
                                  /*low_4gb=*/false,
                                  /*reuse=*/true,
                                  /*reservation=*/nullptr,
                                  &error);
    ok &= Check(zero_tail.IsValid(), error.c_str());
    if (zero_owner.IsValid() && zero_tail.IsValid()) {
      std::vector<uint8_t> zeros(page_size);
      ok &= Check(std::memcmp(zero_tail.Begin(), zeros.data(), page_size) == 0,
                  "fresh anonymous zero-fill tail is not zero");
      ok &= Check(HasProtection(zero_tail.Begin(), PAGE_READONLY),
                  "zero-fill tail did not receive segment protection");
      ok &= Check(HasProtection(zero_owner.Begin(), PAGE_NOACCESS) &&
                      HasProtection(zero_owner.Begin() + 2u * page_size, PAGE_NOACCESS),
                  "zero-fill tail changed an adjacent no-access gap");
    }
    zero_tail.Reset();
    zero_owner.Reset();

    _close(fd);
    ok &= Check(::DeleteFileW(input_path.c_str()) != FALSE,
                "failed to delete the private-copy input file");
  }

  art::MemMap::Shutdown();
  if (!ok) {
    return 1;
  }
  std::printf(
      "W030_PRIVATE_COPY_PASS page=%lu allocation_granularity=%lu "
      "range=checked protections=R_RX_RW gaps=noaccess zero_fill=verified "
      "ownership=shared source=private cache=flushed\n",
      system_info.dwPageSize,
      system_info.dwAllocationGranularity);
  return 0;
}
