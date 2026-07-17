#pragma once
/* Windows multipath only — on Linux/ELF use the system netdb.h. */
#if defined(_WIN32) || defined(ART_TARGET_WINDOWS)
#include <winsock2.h>
#include <ws2tcpip.h>
/* Winsock provides getaddrinfo/freeaddrinfo/gai_strerror */
#ifndef EAI_NODATA
#define EAI_NODATA WSANO_DATA
#endif
#else
#include_next <netdb.h>
#endif
