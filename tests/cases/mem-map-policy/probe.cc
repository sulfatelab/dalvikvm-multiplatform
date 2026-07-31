#include <cstdint>
#include <cstdio>
#include <limits>
#include <string>
#include <sys/mman.h>
#include <vector>

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

bool HasProtection(void* address, DWORD expected) {
  MEMORY_BASIC_INFORMATION info = {};
  return Query(address, &info) && (info.Protect & 0xffu) == expected;
}

uintptr_t AlignUp(uintptr_t value, size_t alignment) {
  return (value + alignment - 1u) & ~(static_cast<uintptr_t>(alignment) - 1u);
}

uintptr_t AlignDown(uintptr_t value, size_t alignment) {
  return value & ~(static_cast<uintptr_t>(alignment) - 1u);
}

bool ReserveExact(uintptr_t address, size_t size, std::vector<void*>* reservations) {
  void* reservation = ::VirtualAlloc(reinterpret_cast<void*>(address),
                                     size,
                                     MEM_RESERVE,
                                     PAGE_NOACCESS);
  if (reservation != reinterpret_cast<void*>(address)) {
    if (reservation != nullptr) {
      ::VirtualFree(reservation, 0u, MEM_RELEASE);
    }
    return false;
  }
  reservations->push_back(reservation);
  return true;
}

bool ReserveLowFreeRanges(bool fragment,
                          std::vector<void*>* reservations,
                          size_t* reservation_count) {
  SYSTEM_INFO system_info = {};
  ::GetSystemInfo(&system_info);
  const size_t granularity = system_info.dwAllocationGranularity;
  const uintptr_t minimum = AlignUp(
      reinterpret_cast<uintptr_t>(system_info.lpMinimumApplicationAddress), granularity);
  constexpr size_t kFragmentChunk = 64u * 1024u * 1024u;

  uintptr_t cursor = minimum;
  while (cursor < k4GB) {
    MEMORY_BASIC_INFORMATION info = {};
    if (!Query(reinterpret_cast<void*>(cursor), &info)) {
      return false;
    }
    const uintptr_t base = reinterpret_cast<uintptr_t>(info.BaseAddress);
    const uintptr_t region_end =
        info.RegionSize >= k4GB - base ? k4GB : base + info.RegionSize;
    if (region_end <= cursor) {
      return false;
    }
    if (info.State != MEM_FREE) {
      cursor = region_end;
      continue;
    }

    const uintptr_t free_begin = AlignUp(cursor > base ? cursor : base, granularity);
    const uintptr_t free_end = AlignDown(region_end, granularity);
    if (free_begin >= free_end) {
      cursor = region_end;
      continue;
    }

    if (fragment) {
      // Leave one allocation-granularity hole, then reserve up to 64 MiB.
      // Repeating this across every low free range guarantees that no
      // two-granularity request can fit while keeping the VirtualAlloc2 search
      // bounded to dozens, rather than thousands, of reservations.
      if (free_end - free_begin <= granularity) {
        cursor = free_end;
        continue;
      }
      const uintptr_t reserve_begin = free_begin + granularity;
      size_t reserve_size = static_cast<size_t>(free_end - reserve_begin);
      if (reserve_size > kFragmentChunk) {
        reserve_size = kFragmentChunk;
      }
      reserve_size = static_cast<size_t>(AlignDown(reserve_size, granularity));
      if (reserve_size == 0u || !ReserveExact(reserve_begin, reserve_size, reservations)) {
        return false;
      }
      cursor = reserve_begin + reserve_size;
    } else {
      const size_t reserve_size = static_cast<size_t>(free_end - free_begin);
      if (!ReserveExact(free_begin, reserve_size, reservations)) {
        return false;
      }
      cursor = free_end;
    }
  }
  *reservation_count = reservations->size();
  return true;
}

bool ReleaseReservations(std::vector<void*>* reservations) {
  bool ok = true;
  for (void* reservation : *reservations) {
    ok &= ::VirtualFree(reservation, 0u, MEM_RELEASE) != FALSE;
  }
  reservations->clear();
  return ok;
}

}  // namespace

int main(int argc, char** argv) {
  bool exhaustive_low_va = false;
  if (argc == 2 && std::string(argv[1]) == "--exhaustive-low-va") {
    exhaustive_low_va = true;
  } else if (argc != 1) {
    std::fprintf(stderr,
                 "usage: windows_x64_w013_mem_map_probe.exe [--exhaustive-low-va]\n");
    return 2;
  }

  art::MemMap::Init();
  bool ok = true;
  std::string error;
  uintptr_t anywhere_address = 0u;
  uintptr_t low_address = 0u;
  bool boundary_tested = false;
  size_t fragment_count = 0u;
  size_t exhaustion_count = 0u;
  constexpr size_t kTransitionCycles = 32u;
  constexpr size_t kDestructionCycles = 128u;

  {
    error.clear();
    art::MemMap empty = art::MemMap::MapAnonymous(
        "w013-empty", 0u, PROT_READ | PROT_WRITE, /*low_4gb=*/false, &error);
    ok &= Check(!empty.IsValid(), "zero-sized mapping unexpectedly succeeded");
    ok &= Check(error == "Empty MemMap requested.", "zero-sized mapping returned wrong error");

    SYSTEM_INFO system_info = {};
    ::GetSystemInfo(&system_info);
    const uintptr_t overflow_begin =
        std::numeric_limits<uintptr_t>::max() - system_info.dwAllocationGranularity + 1u;
    art::MemMap overflow = art::MemMap::MapAnonymous(
        "w013-overflow",
        reinterpret_cast<uint8_t*>(overflow_begin),
        2u * system_info.dwAllocationGranularity,
        PROT_READ | PROT_WRITE,
        /*low_4gb=*/false,
        /*reuse=*/false,
        /*reservation=*/nullptr,
        /*error_msg=*/nullptr);
    ok &= Check(!overflow.IsValid(), "overflowing exact mapping unexpectedly succeeded");
  }

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

  if (exhaustive_low_va) {
    {
      SYSTEM_INFO system_info = {};
      ::GetSystemInfo(&system_info);
      const size_t granularity = system_info.dwAllocationGranularity;
      std::vector<void*> fragments;
      fragments.reserve(128u);
      ok &= Check(ReserveLowFreeRanges(/*fragment=*/true, &fragments, &fragment_count),
                  "failed to fragment the complete low address range");

      art::MemMap fragmented = art::MemMap::MapAnonymous(
          "w013-fragmented-low",
          2u * granularity,
          PROT_READ | PROT_WRITE,
          /*low_4gb=*/true,
          /*error_msg=*/nullptr);
      ok &= Check(!fragmented.IsValid(),
                  "two-granularity low mapping unexpectedly fit in fragmented low VA");
      ok &= Check(ReleaseReservations(&fragments), "failed to release low-VA fragments");

      error.clear();
      art::MemMap recovered = art::MemMap::MapAnonymous(
          "w013-fragmented-recovery",
          2u * granularity,
          PROT_READ | PROT_WRITE,
          /*low_4gb=*/true,
          &error);
      ok &= Check(recovered.IsValid(), error.c_str());
    }

    {
      std::vector<void*> reservations;
      reservations.reserve(1024u);
      ok &= Check(ReserveLowFreeRanges(/*fragment=*/false, &reservations, &exhaustion_count),
                  "failed to reserve the complete low address range");

      art::MemMap exhausted = art::MemMap::MapAnonymous(
          "w013-exhausted-low",
          64u * 1024u,
          PROT_READ | PROT_WRITE,
          /*low_4gb=*/true,
          /*error_msg=*/nullptr);
      ok &= Check(!exhausted.IsValid(),
                  "low mapping unexpectedly succeeded after low-VA exhaustion");

      error.clear();
      art::MemMap high_available = art::MemMap::MapAnonymous(
          "w013-high-after-low-exhaustion",
          64u * 1024u,
          PROT_READ | PROT_WRITE,
          /*low_4gb=*/false,
          &error);
      ok &= Check(high_available.IsValid(), error.c_str());
      ok &= Check(!high_available.IsValid() ||
                      reinterpret_cast<uintptr_t>(high_available.Begin()) >= k4GB,
                  "unrestricted mapping was not high while all low VA was reserved");
      ok &= Check(ReleaseReservations(&reservations), "failed to release exhausted low VA");

      error.clear();
      art::MemMap recovered = art::MemMap::MapAnonymous(
          "w013-exhaustion-recovery",
          64u * 1024u,
          PROT_READ | PROT_WRITE,
          /*low_4gb=*/true,
          &error);
      ok &= Check(recovered.IsValid(), error.c_str());
    }
  }

  {
    const size_t page_size = art::MemMap::GetPageSize();
    error.clear();
    art::MemMap transitions = art::MemMap::MapAnonymous(
        "w013-range-transitions",
        3u * page_size,
        PROT_READ | PROT_WRITE,
        /*low_4gb=*/false,
        &error);
    ok &= Check(transitions.IsValid(), error.c_str());
    if (transitions.IsValid()) {
      uint8_t* first = transitions.Begin();
      uint8_t* middle = first + page_size;
      uint8_t* last = middle + page_size;
      first[0] = 0x11u;
      middle[0] = 0x22u;
      last[0] = 0x33u;
      ok &= Check(transitions.ActivateRange(first, 0u), "zero-length activate failed");
      ok &= Check(transitions.DeactivateRange(first, 0u), "zero-length deactivate failed");
      ok &= Check(transitions.DiscardRange(first, 0u), "zero-length discard failed");
      for (size_t i = 0; i < kTransitionCycles && ok; ++i) {
        ok &= Check(transitions.DiscardRange(middle, page_size), "range discard failed");
        ok &= Check(transitions.DeactivateRange(middle, page_size), "range deactivate failed");
        ok &= Check(HasProtection(middle, PAGE_NOACCESS),
                    "deactivated range is not PAGE_NOACCESS");
        ok &= Check(transitions.DiscardRange(middle, page_size),
                    "discard of deactivated range failed");
        ok &= Check(HasProtection(middle, PAGE_NOACCESS),
                    "discard changed deactivated range protection");
        ok &= Check(first[0] == 0x11u && last[0] == 0x33u,
                    "range transition changed adjacent pages");
        ok &= Check(transitions.ActivateRange(middle, page_size), "range activate failed");
        ok &= Check(HasProtection(middle, PAGE_READWRITE),
                    "activated range is not PAGE_READWRITE");
        middle[0] = static_cast<uint8_t>(0x40u + i);
        ok &= Check(middle[0] == static_cast<uint8_t>(0x40u + i),
                    "activated range is not writable");
      }
    }
  }

  for (size_t i = 0; i < kDestructionCycles && ok; ++i) {
    error.clear();
    art::MemMap mapping = art::MemMap::MapAnonymous(
        "w013-repeated-destruction",
        64u * 1024u,
        PROT_READ | PROT_WRITE,
        /*low_4gb=*/false,
        &error);
    ok &= Check(mapping.IsValid(), error.c_str());
    void* allocation_base = mapping.IsValid() ? mapping.BaseBegin() : nullptr;
    mapping.Reset();
    MEMORY_BASIC_INFORMATION info = {};
    ok &= Check(Query(allocation_base, &info), "VirtualQuery(repeated release) failed");
    ok &= Check(info.State == MEM_FREE, "repeated mapping owner was not wholly released");
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
      ok &= Check((info.Protect & 0xffu) == PAGE_NOACCESS,
                  "logical shrink tail was not deactivated");
      shrunk.Reset();
      ok &= Check(Query(allocation_base, &info), "VirtualQuery(released shrink owner) failed");
      ok &= Check(info.State == MEM_FREE, "logical shrink owner was not wholly released");
    }
  }

  art::MemMap::Shutdown();
  if (!ok) {
    return 1;
  }
  std::printf("W013_MEM_MAP_POLICY_PASS anywhere=%p low=%p boundary=%s transitions=%zu "
              "low_va_stress=%s fragments=%zu exhaustion_reservations=%zu "
              "destruction_cycles=%zu\n",
              reinterpret_cast<void*>(anywhere_address),
              reinterpret_cast<void*>(low_address),
              boundary_tested ? "tested" : "occupied",
              kTransitionCycles,
              exhaustive_low_va ? "exhaustive" : "skipped",
              fragment_count,
              exhaustion_count,
              kDestructionCycles);
  return 0;
}
