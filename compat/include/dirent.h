#pragma once
#if !defined(_WIN32)
#include_next <dirent.h>
#else
#include <stdint.h>
#define DT_UNKNOWN 0
#define DT_FIFO 1
#define DT_CHR 2
#define DT_DIR 4
#define DT_BLK 6
#define DT_REG 8
#define DT_LNK 10
#define DT_SOCK 12
#define DT_WHT 14
struct dirent {
  uint64_t d_ino;
  int64_t d_off;
  uint16_t d_reclen;
  uint8_t d_type;
  char d_name[260];
};
typedef struct DIR DIR;
#ifdef __cplusplus
extern "C" {
#endif
DIR* opendir(const char* name);
struct dirent* readdir(DIR* dirp);
int closedir(DIR* dirp);
#define dirent64 dirent
#define readdir64 readdir
#ifdef __cplusplus
}
#endif
#endif
