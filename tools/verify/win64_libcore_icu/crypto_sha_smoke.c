/* Win64 PE smoke: boringssl SHA-256 of a fixed string. */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <openssl/sha.h>
#include <openssl/crypto.h>

int main(void) {
  static const char *msg = "dalvikvm-multiplatform-L002";
  unsigned char dig[SHA256_DIGEST_LENGTH];
  SHA256((const uint8_t *)msg, strlen(msg), dig);
  printf("crypto.ok=true\n");
  printf("OPENSSL_VERSION=%s\n", OpenSSL_version(OPENSSL_VERSION));
  printf("sha256=");
  for (int i = 0; i < SHA256_DIGEST_LENGTH; i++) printf("%02x", dig[i]);
  printf("\n");
  printf("CryptoSmoke.done=ok\n");
  return 0;
}
