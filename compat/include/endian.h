#pragma once
#if !defined(_WIN32)
#include_next <endian.h>
#else
#include <stdint.h>
#define __LITTLE_ENDIAN 1234
#define __BIG_ENDIAN 4321
#define __BYTE_ORDER __LITTLE_ENDIAN
#define LITTLE_ENDIAN __LITTLE_ENDIAN
#define BIG_ENDIAN __BIG_ENDIAN
#define BYTE_ORDER __BYTE_ORDER
static inline uint16_t htole16(uint16_t x) { return x; }
static inline uint32_t htole32(uint32_t x) { return x; }
static inline uint64_t htole64(uint64_t x) { return x; }
static inline uint16_t le16toh(uint16_t x) { return x; }
static inline uint32_t le32toh(uint32_t x) { return x; }
static inline uint64_t le64toh(uint64_t x) { return x; }
static inline uint16_t htobe16(uint16_t x) {
  return (uint16_t)((x >> 8) | (x << 8));
}
static inline uint32_t htobe32(uint32_t x) {
  return ((x & 0xff) << 24) | ((x & 0xff00) << 8) | ((x & 0xff0000) >> 8) | (x >> 24);
}
static inline uint64_t htobe64(uint64_t x) {
  return ((uint64_t)htobe32((uint32_t)x) << 32) | htobe32((uint32_t)(x >> 32));
}
static inline uint16_t be16toh(uint16_t x) { return htobe16(x); }
static inline uint32_t be32toh(uint32_t x) { return htobe32(x); }
static inline uint64_t be64toh(uint64_t x) { return htobe64(x); }
#endif
