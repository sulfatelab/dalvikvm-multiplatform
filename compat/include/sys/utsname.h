#pragma once
#if !defined(_WIN32)
#include_next <sys/utsname.h>
#else
struct utsname {
  char sysname[65];
  char nodename[65];
  char release[65];
  char version[65];
  char machine[65];
  char domainname[65];
};
#ifdef __cplusplus
extern "C" {
#endif
int uname(struct utsname* buf);
#ifdef __cplusplus
}
#endif
#endif
