#pragma once
#include <winsock2.h>
#include <ws2tcpip.h>
/* Winsock provides getaddrinfo/freeaddrinfo/gai_strerror */
#ifndef EAI_NODATA
#define EAI_NODATA WSANO_DATA
#endif
