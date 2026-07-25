#include <windows.h>

#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>

#include <android-base/logging.h>

#include "gc/allocator/art-dlmalloc.h"
#include "gc/allocator/mspace_morecore.h"

namespace {

using art::gc::allocator::ArtAttachMspaceMoreCoreProvider;
using art::gc::allocator::ArtCreateMspaceWithBase;
using art::gc::allocator::ArtDetachMspaceMoreCoreProvider;
using art::gc::allocator::MspaceMoreCoreProvider;

struct RangeState {
  uint8_t* base;
  uint8_t* current;
  uint8_t* floor;
  uint8_t* limit;
};

class MockProvider final : public MspaceMoreCoreProvider {
 public:
  explicit MockProvider(RangeState* state) : state_(state), expected_mspace_(nullptr), calls_(0u) {}

  void SetExpectedMspace(void* mspace) { expected_mspace_ = mspace; }
  size_t Calls() const { return calls_; }

  void* MoreCore(const void* mspace, intptr_t increment) override {
    CHECK_EQ(mspace, expected_mspace_);
    ++calls_;
    uint8_t* old_end = state_->current;
    if (increment > 0) {
      if (static_cast<size_t>(increment) > static_cast<size_t>(state_->limit - state_->current)) {
        errno = ENOMEM;
        return reinterpret_cast<void*>(~static_cast<uintptr_t>(0u));
      }
      state_->current += increment;
    } else if (increment < 0) {
      const size_t decrement = 0u - static_cast<size_t>(increment);
      if (decrement > static_cast<size_t>(state_->current - state_->floor)) {
        errno = ENOMEM;
        return reinterpret_cast<void*>(~static_cast<uintptr_t>(0u));
      }
      state_->current -= decrement;
    }
    return old_end;
  }

 private:
  RangeState* const state_;
  void* expected_mspace_;
  size_t calls_;
};

struct Arena {
  static constexpr size_t kCapacity = 1u << 20;

  Arena() : base(static_cast<uint8_t*>(VirtualAlloc(
                nullptr, kCapacity, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE))) {
    CHECK(base != nullptr);
    SYSTEM_INFO system_info;
    GetSystemInfo(&system_info);
    page_size = system_info.dwPageSize;
    state = {base, base + page_size, base + page_size, base + kCapacity};
  }

  ~Arena() {
    if (base != nullptr) {
      CHECK_NE(VirtualFree(base, 0u, MEM_RELEASE), 0);
    }
  }

  uint8_t* base;
  size_t page_size;
  RangeState state;
};

void* Create(Arena* arena, MockProvider* provider) {
  void* mspace = ArtCreateMspaceWithBase(arena->base, arena->page_size, provider);
  CHECK(mspace != nullptr);
  provider->SetExpectedMspace(mspace);
  mspace_set_footprint_limit(mspace, Arena::kCapacity);
  return mspace;
}

void ForceGrowth(void* mspace, size_t page_size) {
  void* allocation = mspace_malloc(mspace, page_size * 4u);
  CHECK(allocation != nullptr);
  mspace_free(mspace, allocation);
}

int RunSuccess() {
  Arena arena;
  MockProvider first(&arena.state);
  MockProvider second(&arena.state);
  void* mspace = Create(&arena, &first);

  ForceGrowth(mspace, arena.page_size);
  CHECK_GT(first.Calls(), 0u);
  CHECK_NE(mspace_trim(mspace, 0u), 0);

  ArtDetachMspaceMoreCoreProvider(mspace, &first);
  second.SetExpectedMspace(mspace);
  ArtAttachMspaceMoreCoreProvider(mspace, &second);
  ForceGrowth(mspace, arena.page_size);
  CHECK_GT(second.Calls(), 0u);

  ArtDetachMspaceMoreCoreProvider(mspace, &second);
  destroy_mspace(mspace);
  std::printf("W013_MSPACE_OWNER_PASS first_calls=%zu second_calls=%zu\n",
              first.Calls(),
              second.Calls());
  return 0;
}

void RunDeathCase(const char* mode) {
  Arena arena;
  MockProvider first(&arena.state);
  MockProvider second(&arena.state);

  if (std::strcmp(mode, "missing-provider") == 0) {
    void* mspace = ArtCreateMspaceWithBase(arena.base, arena.page_size, nullptr);
    CHECK(mspace != nullptr);
    mspace_set_footprint_limit(mspace, Arena::kCapacity);
    ForceGrowth(mspace, arena.page_size);
  } else {
    void* mspace = Create(&arena, &first);
    if (std::strcmp(mode, "use-after-detach") == 0) {
      ArtDetachMspaceMoreCoreProvider(mspace, &first);
      ForceGrowth(mspace, arena.page_size);
    } else if (std::strcmp(mode, "wrong-owner-detach") == 0) {
      ArtDetachMspaceMoreCoreProvider(mspace, &second);
    } else if (std::strcmp(mode, "double-attach") == 0) {
      ArtAttachMspaceMoreCoreProvider(mspace, &second);
    }
  }
  LOG(FATAL) << "Death case did not fail: " << mode;
}

}  // namespace

int main(int argc, char** argv) {
  android::base::InitLogging(argv, android::base::StderrLogger);
  if (argc == 1 || std::strcmp(argv[1], "success") == 0) {
    return RunSuccess();
  }
  RunDeathCase(argv[1]);
  return 1;
}
