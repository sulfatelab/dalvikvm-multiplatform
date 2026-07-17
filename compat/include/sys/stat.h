#pragma once
#if !defined(_WIN32)
#include_next <sys/stat.h>
#else
#include_next <sys/stat.h>
/* Windows UCRT has _S_IF* / _S_IS*. Map POSIX S_IS*. */
#ifndef S_IFMT
#define S_IFMT _S_IFMT
#define S_IFDIR _S_IFDIR
#define S_IFCHR _S_IFCHR
#define S_IFIFO _S_IFIFO
#define S_IFREG _S_IFREG
#endif
#ifndef S_ISDIR
#define S_ISDIR(m) (((m) & _S_IFMT) == _S_IFDIR)
#define S_ISCHR(m) (((m) & _S_IFMT) == _S_IFCHR)
#define S_ISFIFO(m) (((m) & _S_IFMT) == _S_IFIFO)
#define S_ISREG(m) (((m) & _S_IFMT) == _S_IFREG)
#define S_ISLNK(m) (0)
#define S_ISSOCK(m) (0)
#define S_ISBLK(m) (0)
#endif
#ifndef S_IRUSR
#define S_IRUSR _S_IREAD
#define S_IWUSR _S_IWRITE
#define S_IXUSR _S_IEXEC
#define S_IRWXU (S_IRUSR|S_IWUSR|S_IXUSR)
#define S_IRGRP S_IRUSR
#define S_IWGRP S_IWUSR
#define S_IXGRP S_IXUSR
#define S_IROTH S_IRUSR
#define S_IWOTH S_IWUSR
#define S_IXOTH S_IXUSR
/* Map timespec fields used by UnixFileSystem. */
#ifndef st_mtim
#define st_atim st_atime
#define st_mtim st_mtime
#define st_ctim st_ctime
/* If code uses st_mtim.tv_sec, provide a helper shape via statement expressions is hard;
 * redefine common pattern in source is better. For MSVC stat, st_mtime is time_t. */
#endif
#endif
#endif
