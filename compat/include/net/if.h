#pragma once
#if !defined(_WIN32)
#include_next <net/if.h>
#else
#include <winsock2.h>
#ifndef IF_NAMESIZE
#define IF_NAMESIZE 16
#endif
#ifndef IFNAMSIZ
#define IFNAMSIZ IF_NAMESIZE
#endif
struct ifreq {
  char ifr_name[IFNAMSIZ];
  union {
    struct sockaddr ifru_addr;
    struct sockaddr ifru_dstaddr;
    struct sockaddr ifru_broadaddr;
    short ifru_flags;
    int ifru_ivalue;
    int ifru_mtu;
    char ifru_slave[IFNAMSIZ];
    char ifru_newname[IFNAMSIZ];
    char* ifru_data;
  } ifr_ifru;
};
#define ifr_addr ifr_ifru.ifru_addr
#define ifr_dstaddr ifr_ifru.ifru_dstaddr
#define ifr_broadaddr ifr_ifru.ifru_broadaddr
#define ifr_flags ifr_ifru.ifru_flags
#define ifr_metric ifr_ifru.ifru_ivalue
#define ifr_mtu ifr_ifru.ifru_mtu
#define ifr_ifindex ifr_ifru.ifru_ivalue
#endif
