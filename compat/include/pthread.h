#pragma once
#if defined(_WIN32)
#include <windows.h>
#include <errno.h>
#include <time.h>
typedef CRITICAL_SECTION pthread_mutex_t;
typedef int pthread_mutexattr_t;
typedef DWORD pthread_t;
typedef DWORD pthread_key_t;
typedef LONG pthread_once_t;
typedef struct { int detachstate; void* stackaddr; size_t stacksize; size_t guardsize; } pthread_attr_t;
typedef CONDITION_VARIABLE pthread_cond_t;
typedef int pthread_condattr_t;
typedef CRITICAL_SECTION pthread_rwlock_t;
typedef int pthread_rwlockattr_t;
/* Zero-init is not a valid CRITICAL_SECTION; ART paths that need static
 * mutexes should call pthread_mutex_init. Provide a sentinel for compile. */
#define PTHREAD_MUTEX_INITIALIZER {0}
#define PTHREAD_ONCE_INIT 0
#define PTHREAD_CREATE_JOINABLE 0
#define PTHREAD_CREATE_DETACHED 1
#define PTHREAD_STACK_MIN 65536
#define PTHREAD_COND_INITIALIZER {0}
#ifdef __cplusplus
extern "C" {
#endif
int pthread_mutex_init(pthread_mutex_t*, const pthread_mutexattr_t*);
int pthread_mutex_destroy(pthread_mutex_t*);
int pthread_mutex_lock(pthread_mutex_t*);
int pthread_mutex_unlock(pthread_mutex_t*);
int pthread_mutex_trylock(pthread_mutex_t*);
int pthread_key_create(pthread_key_t*, void (*)(void*));
int pthread_key_delete(pthread_key_t);
void* pthread_getspecific(pthread_key_t);
int pthread_setspecific(pthread_key_t, const void*);
pthread_t pthread_self(void);
int pthread_equal(pthread_t, pthread_t);
int pthread_once(pthread_once_t*, void (*)(void));
int pthread_setname_np(pthread_t, const char*);
int pthread_getname_np(pthread_t, char*, size_t);
int pthread_rwlock_init(pthread_rwlock_t*, const pthread_rwlockattr_t*);
int pthread_rwlock_destroy(pthread_rwlock_t*);
int pthread_rwlock_rdlock(pthread_rwlock_t*);
int pthread_rwlock_wrlock(pthread_rwlock_t*);
int pthread_rwlock_tryrdlock(pthread_rwlock_t*);
int pthread_rwlock_trywrlock(pthread_rwlock_t*);
int pthread_rwlock_timedrdlock(pthread_rwlock_t*, const struct timespec*);
int pthread_rwlock_timedwrlock(pthread_rwlock_t*, const struct timespec*);
int pthread_rwlock_unlock(pthread_rwlock_t*);
int pthread_condattr_init(pthread_condattr_t*);
int pthread_condattr_destroy(pthread_condattr_t*);
int pthread_condattr_setclock(pthread_condattr_t*, int);
int pthread_cond_init(pthread_cond_t*, const pthread_condattr_t*);
int pthread_cond_destroy(pthread_cond_t*);
int pthread_cond_wait(pthread_cond_t*, pthread_mutex_t*);
int pthread_cond_timedwait(pthread_cond_t*, pthread_mutex_t*, const struct timespec*);
int pthread_cond_signal(pthread_cond_t*);
int pthread_cond_broadcast(pthread_cond_t*);
int pthread_create(pthread_t*, const pthread_attr_t*, void* (*)(void*), void*);
int pthread_join(pthread_t, void**);
int pthread_detach(pthread_t);
int pthread_attr_init(pthread_attr_t*);
int pthread_attr_destroy(pthread_attr_t*);
int pthread_attr_setdetachstate(pthread_attr_t*, int);
int pthread_kill(pthread_t, int);
int pthread_getattr_np(pthread_t, pthread_attr_t*);
int pthread_attr_getguardsize(const pthread_attr_t*, size_t*);
int pthread_attr_getstack(const pthread_attr_t*, void**, size_t*);
int pthread_attr_setstacksize(pthread_attr_t*, size_t);
int pthread_attr_setstack(pthread_attr_t*, void*, size_t);
#ifdef __cplusplus
}
#endif
#else
#include_next <pthread.h>
#endif
