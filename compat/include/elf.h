#pragma once
#if !defined(_WIN32)
#include_next <elf.h>
#else
#include <stdint.h>
typedef uint16_t Elf32_Half;
typedef uint32_t Elf32_Word;
typedef int32_t Elf32_Sword;
typedef uint32_t Elf32_Addr;
typedef uint32_t Elf32_Off;
typedef uint16_t Elf64_Half;
typedef uint32_t Elf64_Word;
typedef int32_t Elf64_Sword;
typedef uint64_t Elf64_Xword;
typedef int64_t Elf64_Sxword;
typedef uint64_t Elf64_Addr;
typedef uint64_t Elf64_Off;
#define EI_NIDENT 16
#define EI_MAG0 0
#define EI_MAG1 1
#define EI_MAG2 2
#define EI_MAG3 3
#define EI_CLASS 4
#define EI_DATA 5
#define EI_VERSION 6
#define EI_OSABI 7
#define ELFMAG0 0x7f
#define ELFMAG1 'E'
#define ELFMAG2 'L'
#define ELFMAG3 'F'
#define ELFMAG "\177ELF"
#define SELFMAG 4
#define ELFCLASSNONE 0
#define ELFCLASS32 1
#define ELFCLASS64 2
#define ELFDATANONE 0
#define ELFDATA2LSB 1
#define ELFDATA2MSB 2
#define EV_CURRENT 1
#define ET_NONE 0
#define ET_REL 1
#define ET_EXEC 2
#define ET_DYN 3
#define ET_CORE 4
#define EM_NONE 0
#define EM_386 3
#define EM_ARM 40
#define EM_X86_64 62
#define EM_AARCH64 183
#define EM_MIPS 8
#define EM_RISCV 243
#define PT_NULL 0
#define PT_LOAD 1
#define PT_DYNAMIC 2
#define PT_INTERP 3
#define PT_NOTE 4
#define PT_SHLIB 5
#define PT_PHDR 6
#define PT_TLS 7
#define PT_GNU_EH_FRAME 0x6474e550
#define PT_GNU_STACK 0x6474e551
#define PT_GNU_RELRO 0x6474e552
#define SHT_NULL 0
#define SHT_PROGBITS 1
#define SHT_SYMTAB 2
#define SHT_STRTAB 3
#define SHT_RELA 4
#define SHT_HASH 5
#define SHT_DYNAMIC 6
#define SHT_NOTE 7
#define SHT_NOBITS 8
#define SHT_REL 9
#define SHT_DYNSYM 11
#define DT_NULL 0
#define DT_NEEDED 1
#define DT_PLTRELSZ 2
#define DT_PLTGOT 3
#define DT_HASH 4
#define DT_STRTAB 5
#define DT_SYMTAB 6
#define DT_RELA 7
#define DT_RELASZ 8
#define DT_RELAENT 9
#define DT_STRSZ 10
#define DT_SYMENT 11
#define DT_INIT 12
#define DT_FINI 13
#define DT_SONAME 14
#define DT_RPATH 15
#define DT_SYMBOLIC 16
#define DT_REL 17
#define DT_RELSZ 18
#define DT_RELENT 19
#define DT_PLTREL 20
#define DT_DEBUG 21
#define DT_TEXTREL 22
#define DT_JMPREL 23
#define DT_BIND_NOW 24
#define DT_INIT_ARRAY 25
#define DT_FINI_ARRAY 26
#define DT_INIT_ARRAYSZ 27
#define DT_FINI_ARRAYSZ 28
#define DT_RUNPATH 29
#define DT_FLAGS 30
#define DT_GNU_HASH 0x6ffffef5
#define PF_X 1
#define PF_W 2
#define PF_R 4
#define STT_NOTYPE 0
#define STT_OBJECT 1
#define STT_FUNC 2
#define STT_SECTION 3
#define STT_FILE 4
#define STB_LOCAL 0
#define STB_GLOBAL 1
#define STB_WEAK 2
#define SHN_UNDEF 0
#define SHN_ABS 0xfff1
#define SHN_COMMON 0xfff2
#define NT_PRSTATUS 1
#define NT_FPREGSET 2
#define NT_PRPSINFO 3
#define NT_GNU_BUILD_ID 3
#define NT_ARM_VFP 0x400
typedef struct {
  unsigned char e_ident[EI_NIDENT];
  Elf64_Half e_type; Elf64_Half e_machine; Elf64_Word e_version;
  Elf64_Addr e_entry; Elf64_Off e_phoff; Elf64_Off e_shoff;
  Elf64_Word e_flags; Elf64_Half e_ehsize; Elf64_Half e_phentsize;
  Elf64_Half e_phnum; Elf64_Half e_shentsize; Elf64_Half e_shnum; Elf64_Half e_shstrndx;
} Elf64_Ehdr;
typedef struct {
  Elf64_Word p_type; Elf64_Word p_flags; Elf64_Off p_offset;
  Elf64_Addr p_vaddr; Elf64_Addr p_paddr; Elf64_Xword p_filesz;
  Elf64_Xword p_memsz; Elf64_Xword p_align;
} Elf64_Phdr;
typedef struct {
  Elf64_Word sh_name; Elf64_Word sh_type; Elf64_Xword sh_flags;
  Elf64_Addr sh_addr; Elf64_Off sh_offset; Elf64_Xword sh_size;
  Elf64_Word sh_link; Elf64_Word sh_info; Elf64_Xword sh_addralign; Elf64_Xword sh_entsize;
} Elf64_Shdr;
typedef struct {
  Elf64_Word st_name; unsigned char st_info; unsigned char st_other;
  Elf64_Half st_shndx; Elf64_Addr st_value; Elf64_Xword st_size;
} Elf64_Sym;
typedef struct { Elf64_Addr r_offset; Elf64_Xword r_info; } Elf64_Rel;
typedef struct { Elf64_Addr r_offset; Elf64_Xword r_info; Elf64_Sxword r_addend; } Elf64_Rela;
typedef struct { Elf64_Sxword d_tag; union { Elf64_Xword d_val; Elf64_Addr d_ptr; } d_un; } Elf64_Dyn;
typedef struct { Elf64_Word n_namesz; Elf64_Word n_descsz; Elf64_Word n_type; } Elf64_Nhdr;
typedef struct {
  unsigned char e_ident[EI_NIDENT];
  Elf32_Half e_type; Elf32_Half e_machine; Elf32_Word e_version;
  Elf32_Addr e_entry; Elf32_Off e_phoff; Elf32_Off e_shoff;
  Elf32_Word e_flags; Elf32_Half e_ehsize; Elf32_Half e_phentsize;
  Elf32_Half e_phnum; Elf32_Half e_shentsize; Elf32_Half e_shnum; Elf32_Half e_shstrndx;
} Elf32_Ehdr;
typedef struct {
  Elf32_Word p_type; Elf32_Off p_offset; Elf32_Addr p_vaddr; Elf32_Addr p_paddr;
  Elf32_Word p_filesz; Elf32_Word p_memsz; Elf32_Word p_flags; Elf32_Word p_align;
} Elf32_Phdr;
typedef struct {
  Elf32_Word sh_name; Elf32_Word sh_type; Elf32_Word sh_flags; Elf32_Addr sh_addr;
  Elf32_Off sh_offset; Elf32_Word sh_size; Elf32_Word sh_link; Elf32_Word sh_info;
  Elf32_Word sh_addralign; Elf32_Word sh_entsize;
} Elf32_Shdr;
typedef struct {
  Elf32_Word st_name; Elf32_Addr st_value; Elf32_Word st_size;
  unsigned char st_info; unsigned char st_other; Elf32_Half st_shndx;
} Elf32_Sym;
typedef struct { Elf32_Addr r_offset; Elf32_Word r_info; } Elf32_Rel;
typedef struct { Elf32_Addr r_offset; Elf32_Word r_info; Elf32_Sword r_addend; } Elf32_Rela;
typedef struct { Elf32_Sword d_tag; union { Elf32_Word d_val; Elf32_Addr d_ptr; } d_un; } Elf32_Dyn;
typedef struct { Elf32_Word n_namesz; Elf32_Word n_descsz; Elf32_Word n_type; } Elf32_Nhdr;
#define ELF64_R_SYM(i) ((i) >> 32)
#define ELF64_R_TYPE(i) ((i) & 0xffffffffULL)
#define ELF32_R_SYM(i) ((i) >> 8)
#define ELF32_R_TYPE(i) ((unsigned char)(i))
#define ELF64_ST_BIND(i) ((i) >> 4)
#define ELF64_ST_TYPE(i) ((i) & 0xf)
#define ELF32_ST_BIND(i) ((i) >> 4)
#define ELF32_ST_TYPE(i) ((i) & 0xf)
#define ELF64_ST_INFO(b,t) (((b)<<4)+((t)&0xf))
#define ELF32_ST_INFO(b,t) (((b)<<4)+((t)&0xf))

/* Section flags / OSABI extras required by ART elf_builder. */
#ifndef SHF_WRITE
#define SHF_WRITE            (1 << 0)
#define SHF_ALLOC            (1 << 1)
#define SHF_EXECINSTR        (1 << 2)
#define SHF_MERGE            (1 << 4)
#define SHF_STRINGS          (1 << 5)
#define SHF_INFO_LINK        (1 << 6)
#define SHF_LINK_ORDER       (1 << 7)
#define SHF_OS_NONCONFORMING (1 << 8)
#define SHF_GROUP            (1 << 9)
#define SHF_TLS              (1 << 10)
#define SHF_COMPRESSED       (1 << 11)
#define SHF_MASKOS           0x0ff00000
#define SHF_MASKPROC         0xf0000000
#endif
#ifndef EI_ABIVERSION
#define EI_ABIVERSION 8
#define EI_PAD 9
#endif
#ifndef ELFOSABI_NONE
#define ELFOSABI_NONE 0
#define ELFOSABI_SYSV 0
#define ELFOSABI_GNU 3
#define ELFOSABI_LINUX ELFOSABI_GNU
#define ELFOSABI_ARM_AEABI 64
#define ELFOSABI_ARM 97
#define ELFOSABI_STANDALONE 255
#endif
#ifndef EF_ARM_EABI_VER5
#define EF_ARM_EABIMASK 0xFF000000
#define EF_ARM_EABI_UNKNOWN 0x00000000
#define EF_ARM_EABI_VER1 0x01000000
#define EF_ARM_EABI_VER2 0x02000000
#define EF_ARM_EABI_VER3 0x03000000
#define EF_ARM_EABI_VER4 0x04000000
#define EF_ARM_EABI_VER5 0x05000000
#endif
#ifndef SHT_INIT_ARRAY
#define SHT_INIT_ARRAY 14
#define SHT_FINI_ARRAY 15
#define SHT_PREINIT_ARRAY 16
#define SHT_GROUP 17
#define SHT_GNU_HASH 0x6ffffff6
#endif
#ifndef STT_TLS
#define STT_COMMON 5
#define STT_TLS 6
#define STT_GNU_IFUNC 10
#endif
#ifndef STV_DEFAULT
#define STV_DEFAULT 0
#define STV_INTERNAL 1
#define STV_HIDDEN 2
#define STV_PROTECTED 3
#endif
#endif
