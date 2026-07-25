#include <cstdint>
#include <cstdio>
#include <limits>
#include <string>
#include <sys/mman.h>

#include <windows.h>

#include "base/mem_map.h"

namespace {

constexpr uintptr_t k4GB = UINT64_C(0x100000000);

bool Check(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "W013_MEM_MAP_POLICY_FAIL: %s\n", message);
  }
  return condition;
}

bool Query(void* address, MEMORY_BASIC_INFORMATION* info) {
  return ::VirtualQuery(address, info, sizeof(*info)) == sizeof(*info);
}

}  // namespace

int main() {
  art::MemMap::Init();
  bool ok = true;
  std::string error;
  uintptr_t anywhere_address = 0u;
  uintptr_t low_address = 0u;
  bool boundary_tested = false;

  {
    constexpr size_t kAllocationSize = 64u * 1024u;
    art::MemMap anywhere = art::MemMap::MapAnonymous(
        "w013-anywhere", kAllocationSize, PROT_READ | PROT_WRITE, /*low_4gb=*/false, &error);
    ok &= Check(anywhere.IsValid(), error.c_str());
    if (anywhere.IsValid()) {
      MEMORY_BASIC_INFORMATION info = {};
      ok &= Check(Query(anywhere.Begin(), &info), "VirtualQuery(anywhere) failed");
      ok &= Check(info.Type == MEM_PRIVATE, "anywhere mapping is not MEM_PRIVATE");
      ok &= Check(info.AllocationBase == anywhere.BaseBegin(),
                  "anywhere allocation base does not match MemMap base");
      anywhere_address = reinterpret_cast<uintptr_t>(anywhere.Begin());
    }
    anywhere.Reset();

    error.clear();
    art::MemMap exact = art::MemMap::MapAnonymous(
        "w013-exact",
        reinterpret_cast<uint8_t*>(anywhere_address),
        kAllocationSize,
        PROT_READ | PROT_WRITE,
        /*low_4gb=*/false,
        /*reuse=*/false,
        /*reservation=*/nullptr,
        &error);
    ok &= Check(exact.IsValid(), error.c_str());
    ok &= Check(!exact.IsValid() || reinterpret_cast<uintptr_t>(exact.Begin()) == anywhere_address,
                "exact mapping moved to a different address");

    art::MemMap collision = art::MemMap::MapAnonymous(
        "w013-exact-collision",
        reinterpret_cast<uint8_t*>(anywhere_address),
        kAllocationSize,
        PROT_READ | PROT_WRITE,
        /*low_4gb=*/false,
        /*reuse=*/false,
        /*reservation=*/nullptr,
        /*error_msg=*/nullptr);
    ok &= Check(!collision.IsValid(), "exact collision unexpectedly succeeded");
  }

  {
    constexpr size_t kAllocationSize = 64u * 1024u;
    error.clear();
    art::MemMap low = art::MemMap::MapAnonymous(
        "w013-low", kAllocationSize, PROT_READ | PROT_WRITE, /*low_4gb=*/true, &error);
    ok &= Check(low.IsValid(), error.c_str());
    if (low.IsValid()) {
      low_address = reinterpret_cast<uintptr_t>(low.Begin());
      ok &= Check(low_address < k4GB && kAllocationSize <= k4GB - low_address,
                  "low mapping extends beyond 4 GiB");
    }
    low.Reset();

    error.clear();
    art::MemMap exact_low = art::MemMap::MapAnonymous(
        "w013-exact-low",
        reinterpret_cast<uint8_t*>(low_address),
        kAllocationSize,
        PROT_READ | PROT_WRITE,
        /*low_4gb=*/true,
        /*reuse=*/false,
        /*reservation=*/nullptr,
        &error);
    ok &= Check(exact_low.IsValid(), error.c_str());
    ok &= Check(!exact_low.IsValid() || reinterpret_cast<uintptr_t>(exact_low.Begin()) == low_address,
                "exact low mapping moved to a different address");

    constexpr uintptr_t kBoundaryAddress = k4GB - kAllocationSize;
    MEMORY_BASIC_INFORMATION boundary_info = {};
    if (Query(reinterpret_cast<void*>(kBoundaryAddress), &boundary_info) &&
        boundary_info.State == MEM_FREE &&
        reinterpret_cast<uintptr_t>(boundary_info.BaseAddress) <= kBoundaryAddress &&
        boundary_info.RegionSize >=
            k4GB - reinterpret_cast<uintptr_t>(boundary_info.BaseAddress)) {
      boundary_tested = true;
      error.clear();
      art::MemMap boundary = art::MemMap::MapAnonymous(
          "w013-low-boundary",
          reinterpret_cast<uint8_t*>(kBoundaryAddress),
          kAllocationSize,
          PROT_READ | PROT_WRITE,
          /*low_4gb=*/true,
          /*reuse=*/false,
          /*reservation=*/nullptr,
          &error);
      ok &= Check(boundary.IsValid(), error.c_str());
      ok &= Check(!boundary.IsValid() || reinterpret_cast<uintptr_t>(boundary.End()) == k4GB,
                  "mapping ending exactly at 4 GiB was rejected or truncated");
    }
  }

  {
    constexpr size_t kAlignment = 2u * 1024u * 1024u;
    error.clear();
    art::MemMap aligned = art::MemMap::MapAnonymousAligned(
        "w013-aligned",
        3u * art::MemMap::GetPageSize(),
        PROT_READ | PROT_WRITE,
        /*low_4gb=*/false,
        kAlignment,
        &error);
    ok &= Check(aligned.IsValid(), error.c_str());
    if (aligned.IsValid()) {
      MEMORY_BASIC_INFORMATION info = {};
      ok &= Check((reinterpret_cast<uintptr_t>(aligned.Begin()) & (kAlignment - 1u)) == 0u,
                  "aligned mapping has the wrong base alignment");
      ok &= Check(Query(aligned.Begin(), &info), "VirtualQuery(aligned) failed");
      ok &= Check(info.AllocationBase == aligned.Begin(),
                  "aligned mapping used an over-allocation interior pointer");
    }
  }

  {
    const size_t page_size = art::MemMap::GetPageSize();
    error.clear();
    art::MemMap reservation = art::MemMap::MapAnonymous(
        "w013-reservation", 3u * page_size, PROT_NONE, /*low_4gb=*/false, &error);
    ok &= Check(reservation.IsValid(), error.c_str());
    void* allocation_base = nullptr;
    if (reservation.IsValid()) {
      MEMORY_BASIC_INFORMATION info = {};
      ok &= Check(Query(reservation.Begin(), &info), "VirtualQuery(reservation) failed");
      allocation_base = info.AllocationBase;
    }

    uint8_t* first_address = reservation.IsValid() ? reservation.Begin() : nullptr;
    error.clear();
    art::MemMap first = art::MemMap::MapAnonymous(
        "w013-reservation-first",
        first_address,
        page_size,
        PROT_READ | PROT_WRITE,
        /*low_4gb=*/false,
        /*reuse=*/false,
        reservation.IsValid() ? &reservation : nullptr,
        &error);
    ok &= Check(first.IsValid(), error.c_str());

    uint8_t* second_address = reservation.IsValid() ? reservation.Begin() : nullptr;
    const size_t second_size = reservation.IsValid() ? reservation.Size() : 0u;
    error.clear();
    art::MemMap second = art::MemMap::MapAnonymous(
        "w013-reservation-second",
        second_address,
        second_size,
        PROT_READ | PROT_WRITE,
        /*low_4gb=*/false,
        /*reuse=*/false,
        reservation.IsValid() ? &reservation : nullptr,
        &error);
    ok &= Check(second.IsValid(), error.c_str());
    ok &= Check(!reservation.IsValid(), "reservation was not fully transferred");

    if (first.IsValid() && second.IsValid()) {
      first.Begin()[0] = 0x31u;
      second.Begin()[0] = 0x52u;
      first.Reset();
      ok &= Check(second.Begin()[0] == 0x52u,
                  "destroying one logical view released the shared owner");
      second.Reset();
      MEMORY_BASIC_INFORMATION info = {};
      ok &= Check(Query(allocation_base, &info), "VirtualQuery(released owner) failed");
      ok &= Check(info.State == MEM_FREE, "shared reservation owner was not released exactly once");
    }
  }

  {
    const size_t page_size = art::MemMap::GetPageSize();
    error.clear();
    art::MemMap owner = art::MemMap::MapAnonymous(
        "w013-reuse-owner", 64u * 1024u, PROT_READ | PROT_WRITE, /*low_4gb=*/false, &error);
    ok &= Check(owner.IsValid(), error.c_str());
    void* allocation_base = owner.IsValid() ? owner.BaseBegin() : nullptr;

    error.clear();
    art::MemMap reuse = art::MemMap::MapAnonymous(
        "w013-reuse-view",
        owner.IsValid() ? owner.Begin() : nullptr,
        page_size,
        PROT_READ | PROT_WRITE,
        /*low_4gb=*/false,
        /*reuse=*/true,
        /*reservation=*/nullptr,
        &error);
    ok &= Check(reuse.IsValid(), error.c_str());
    if (owner.IsValid() && reuse.IsValid()) {
      reuse.Begin()[0] = 0x71u;
      owner.Reset();
      ok &= Check(reuse.Begin()[0] == 0x71u,
                  "reuse view did not retain the shared Windows owner");
      reuse.Reset();
      MEMORY_BASIC_INFORMATION info = {};
      ok &= Check(Query(allocation_base, &info), "VirtualQuery(released reuse owner) failed");
      ok &= Check(info.State == MEM_FREE, "reuse owner was not released exactly once");
    }
  }

  {
    const size_t page_size = art::MemMap::GetPageSize();
    error.clear();
    art::MemMap shrunk = art::MemMap::MapAnonymous(
        "w013-logical-shrink", 3u * page_size, PROT_READ | PROT_WRITE, /*low_4gb=*/false, &error);
    ok &= Check(shrunk.IsValid(), error.c_str());
    void* allocation_base = shrunk.IsValid() ? shrunk.BaseBegin() : nullptr;
    uint8_t* old_tail = shrunk.IsValid() ? shrunk.Begin() + 2u * page_size : nullptr;
    if (shrunk.IsValid()) {
      shrunk.SetSize(page_size);
      ok &= Check(shrunk.Size() == page_size, "logical shrink reported the wrong size");
      MEMORY_BASIC_INFORMATION info = {};
      ok &= Check(Query(old_tail, &info), "VirtualQuery(logical shrink tail) failed");
      ok &= Check(info.State != MEM_FREE,
                  "logical shrink partially released a VirtualAlloc reservation");
      shrunk.Reset();
      ok &= Check(Query(allocation_base, &info), "VirtualQuery(released shrink owner) failed");
      ok &= Check(info.State == MEM_FREE, "logical shrink owner was not wholly released");
    }
  }

  art::MemMap::Shutdown();
  if (!ok) {
    return 1;
  }
  std::printf("W013_MEM_MAP_POLICY_PASS anywhere=%p low=%p boundary=%s\n",
              reinterpret_cast<void*>(anywhere_address),
              reinterpret_cast<void*>(low_address),
              boundary_tested ? "tested" : "occupied");
  return 0;
}
