#pragma once
#if !defined(_WIN32)
#include_next <netinet/tcp.h>
#else
#include <winsock2.h>
#ifndef TCP_NODELAY
#define TCP_NODELAY 0x0001
#endif
#endif
