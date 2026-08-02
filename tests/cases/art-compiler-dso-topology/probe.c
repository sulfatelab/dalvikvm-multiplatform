#include <dlfcn.h>
#include <stdio.h>

int main(int argc, char** argv) {
  if (argc != 3) {
    fprintf(stderr, "usage: %s <runtime-dso> <compiler-dso>\n", argv[0]);
    return 2;
  }

  void* runtime = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
  if (runtime == NULL) {
    fprintf(stderr, "runtime load failed: %s\n", dlerror());
    return 3;
  }

  void* compiler = dlopen(argv[2], RTLD_NOW | RTLD_LOCAL);
  if (compiler == NULL) {
    fprintf(stderr, "compiler load failed: %s\n", dlerror());
    return 4;
  }

  puts("art-compiler-dso-topology runtime=loaded compiler=loaded");
  return 0;
}
