#pragma once
#if !defined(_WIN32)
#include_next <netinet/in.h>
#else
#include <winsock2.h>
#include <ws2tcpip.h>
/* Oracle openjdk uses SOCKADDR_IN6 on WIN32 */
#ifndef SOCKADDR_IN6
#define SOCKADDR_IN6 sockaddr_in6
#endif
/* Winsock provides in_addr, in6_addr, sockaddr_in/in6, IPPROTO_*, INADDR_*. */
#ifndef IP_MULTICAST_IF
#define IP_MULTICAST_IF 9
#endif
#ifndef IP_MULTICAST_TTL
#define IP_MULTICAST_TTL 10
#endif
#ifndef IP_MULTICAST_LOOP
#define IP_MULTICAST_LOOP 11
#endif
#ifndef IP_ADD_MEMBERSHIP
#define IP_ADD_MEMBERSHIP 12
#endif
#ifndef IP_DROP_MEMBERSHIP
#define IP_DROP_MEMBERSHIP 13
#endif
#ifndef IPV6_MULTICAST_IF
#define IPV6_MULTICAST_IF 9
#endif
#ifndef IPV6_JOIN_GROUP
#define IPV6_JOIN_GROUP 12
#endif
#ifndef IPV6_LEAVE_GROUP
#define IPV6_LEAVE_GROUP 13
#endif
#ifndef IPV6_V6ONLY
#define IPV6_V6ONLY 27
#endif
#endif
