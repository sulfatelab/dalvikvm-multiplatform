/* Minimal liblog stub for the libbase verification harness.
 *
 * Not a real implementation — just enough symbols for base.so to link against a
 * `log` target in isolation. The real logging/liblog module replaces this once
 * it is converted. Signatures follow android/log.h closely enough to link.
 */
#include <stdarg.h>

int __android_log_print(int prio, const char* tag, const char* fmt, ...) {
    (void)prio; (void)tag; (void)fmt;
    return 0;
}

void __android_log_assert(const char* cond, const char* tag,
                          const char* fmt, ...) {
    (void)cond; (void)tag; (void)fmt;
}

int __android_log_write(int prio, const char* tag, const char* text) {
    (void)prio; (void)tag; (void)text;
    return 0;
}

struct __android_log_message;
void __android_log_logd_logger(const struct __android_log_message* m) { (void)m; }
void __android_log_set_logger(void* logger) { (void)logger; }
void __android_log_default_aborter(const char* abort_message) { (void)abort_message; }
void __android_log_set_aborter(void* aborter) { (void)aborter; }
int __android_log_is_loggable(int prio, const char* tag, int default_prio) {
    (void)prio; (void)tag; (void)default_prio;
    return 1;
}
