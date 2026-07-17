/* Win64 compat: glibc byteswap.h */
#pragma once
#include <stdint.h>
#ifdef _MSC_VER
#include <stdlib.h>
#define bswap_16 _byteswap_ushort
#define bswap_32 _byteswap_ulong
#define bswap_64 _byteswap_uint64
#else
static inline uint16_t bswap_16(uint16_t x) {
  return (uint16_t)((x << 8) | (x >> 8));
}
static inline uint32_t bswap_32(uint32_t x) {
  return ((x & 0xff000000u) >> 24) | ((x & 0x00ff0000u) >> 8) |
         ((x & 0x0000ff00u) << 8) | ((x & 0x000000ffu) << 24);
}
static inline uint64_t bswap_64(uint64_t x) {
  return ((uint64_t)bswap_32((uint32_t)x) << 32) | bswap_32((uint32_t)(x >> 32));
}
#endif
