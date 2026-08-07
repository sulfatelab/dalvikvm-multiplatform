#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include "arch/instruction_set.h"
#include "base/globals.h"
#include "elf/elf_builder.h"
#include "stream/vector_output_stream.h"

namespace {

using art::ElfBuilder;
using art::ElfTypes64;
using art::InstructionSet;
using art::VectorOutputStream;

constexpr size_t kRoDataSize = 0x208u;
constexpr size_t kTextSize = 0x180u;
constexpr size_t kDataImgRelRoSize = 0x20u;
constexpr size_t kWindowsUnwindSize = 0x34u;
constexpr size_t kWindowsCfgSize = 0x38u;
constexpr size_t kBssSize = 0x40u;

bool WriteSection(ElfBuilder<ElfTypes64>::Section *section, size_t size,
                  uint8_t fill) {
  std::vector<uint8_t> bytes(size, fill);
  section->Start();
  bool success = section->WriteFully(bytes.data(), bytes.size());
  section->End();
  return success;
}

bool WriteLayout(const std::filesystem::path &path, bool data_img_rel_ro,
                 bool windows_unwind, bool windows_cfg) {
  std::vector<uint8_t> elf;
  VectorOutputStream output(path.string(), &elf);
  ElfBuilder<ElfTypes64> builder(InstructionSet::kX86_64, &output);
  builder.Start();

  // Reserve the full Windows metadata symbol capacity for every case. The
  // `neither` cases consequently exercise enabled-mode/empty-payload behavior.
  builder.ReserveSpaceForDynamicSection(path.string(),
                                        /*extra_dynamic_symbols=*/4u);
  builder.GetRoData()->Start();
  builder.PrepareDynamicSection(path.string(), kRoDataSize, kTextSize,
                                data_img_rel_ro ? kDataImgRelRoSize : 0u,
                                data_img_rel_ro ? kDataImgRelRoSize : 0u,
                                windows_unwind ? kWindowsUnwindSize : 0u,
                                windows_cfg ? kWindowsCfgSize : 0u, kBssSize,
                                /*bss_methods_offset=*/0u,
                                /*bss_roots_offset=*/0u,
                                /*dex_size=*/0u);

  std::vector<uint8_t> rodata(kRoDataSize, 0x11u);
  if (!builder.GetRoData()->WriteFully(rodata.data(), rodata.size())) {
    return false;
  }
  builder.GetRoData()->End();
  if (!WriteSection(builder.GetText(), kTextSize, 0x22u)) {
    return false;
  }
  if (data_img_rel_ro &&
      !WriteSection(builder.GetDataImgRelRo(), kDataImgRelRoSize, 0x33u)) {
    return false;
  }
  if (windows_unwind &&
      !WriteSection(builder.GetWindowsUnwind(), kWindowsUnwindSize, 0x44u)) {
    return false;
  }
  if (windows_cfg &&
      !WriteSection(builder.GetWindowsCfg(), kWindowsCfgSize, 0x55u)) {
    return false;
  }
  builder.WriteDynamicSection();
  builder.End();

  std::ofstream destination(path, std::ios::binary | std::ios::trunc);
  destination.write(reinterpret_cast<const char *>(elf.data()), elf.size());
  return destination.good();
}

} // namespace

int main(int argc, char **argv) {
  if (argc != 2) {
    std::cerr << "usage: w032cfglayoutprobe <output-directory>\n";
    return 2;
  }
  const std::filesystem::path output = argv[1];
  std::error_code error;
  std::filesystem::create_directories(output, error);
  if (error) {
    std::cerr << "failed to create output directory: " << error.message()
              << '\n';
    return 1;
  }

  size_t cases = 0u;
  for (bool data_img_rel_ro : {false, true}) {
    for (unsigned metadata = 0u; metadata != 4u; ++metadata) {
      const bool windows_unwind = (metadata & 1u) != 0u;
      const bool windows_cfg = (metadata & 2u) != 0u;
      const char *metadata_name = metadata == 0u   ? "neither"
                                  : metadata == 1u ? "unwind"
                                  : metadata == 2u ? "cfg"
                                                   : "both";
      std::string name = std::string(metadata_name) +
                         (data_img_rel_ro ? "-relro.oat" : "-no-relro.oat");
      if (!WriteLayout(output / name, data_img_rel_ro, windows_unwind,
                       windows_cfg)) {
        std::cerr << "failed to write " << name << '\n';
        return 1;
      }
      ++cases;
    }
  }
  std::cout << "W032_CFG_LAYOUT_EMIT_PASS cases=" << cases
            << " segment_alignment=" << art::kElfSegmentAlignment << '\n';
  return 0;
}
