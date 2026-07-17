#pragma once
#if !defined(_WIN32)
#include_next <arpa/inet.h>
#else
#include <winsock2.h>
#include <ws2tcpip.h>
/* inet_ntop/pton/addr provided by Winsock. */
#endif
