#include <errno.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <windows.h>

enum {
  kJoinStressCount = 512,
  kDetachStressCount = 128,
};

typedef struct {
  HANDLE entered;
  HANDLE release;
  size_t requested_size;
  size_t observed_size;
  void* expected_result;
  int print_bounds;
  volatile LONG failures;
} thread_case_t;

static volatile LONG g_failures;
static size_t g_default_stack_size;

static void Fail(const char* test, const char* detail) {
  fprintf(stderr, "FAIL %s: %s (winerr=%lu errno=%d)\n",
          test,
          detail,
          GetLastError(),
          errno);
  InterlockedIncrement(&g_failures);
}

static void CaseFail(thread_case_t* test_case, const char* detail) {
  Fail("worker", detail);
  InterlockedIncrement(&test_case->failures);
}

static int ValidateCurrentStack(thread_case_t* test_case, const char* label) {
  pthread_t first = pthread_self();
  pthread_t second = pthread_self();
  if (first == NULL || second == NULL || !pthread_equal(first, second)) {
    CaseFail(test_case, "pthread_self identity is not stable");
    return 0;
  }
  if (pthread_gettid_np(first) != GetCurrentThreadId()) {
    CaseFail(test_case, "pthread_gettid_np does not match GetCurrentThreadId");
  }

  pthread_attr_t attr;
  if (pthread_getattr_np(first, &attr) != 0) {
    CaseFail(test_case, "pthread_getattr_np rejected the current system stack");
    return 0;
  }

  void* attr_base = NULL;
  size_t attr_size = 0;
  size_t guard_size = 0;
  if (pthread_attr_getstack(&attr, &attr_base, &attr_size) != 0 ||
      pthread_attr_getguardsize(&attr, &guard_size) != 0) {
    CaseFail(test_case, "pthread stack attributes could not be read");
  }

  ULONG_PTR low = 0;
  ULONG_PTR high = 0;
  GetCurrentThreadStackLimits(&low, &high);
  SYSTEM_INFO system_info;
  GetSystemInfo(&system_info);
  volatile char stack_probe = 0;
  uintptr_t sp = (uintptr_t)&stack_probe;
  if ((ULONG_PTR)attr_base != low ||
      attr_size != (size_t)(high - low) ||
      sp <= low || sp >= high) {
    CaseFail(test_case, "reported bounds differ from GetCurrentThreadStackLimits");
  }
  if (guard_size != (size_t)system_info.dwPageSize) {
    CaseFail(test_case, "reported excluded-low prefix is not one page");
  }
  if (pthread_attr_destroy(&attr) != 0) {
    CaseFail(test_case, "pthread_attr_destroy failed");
  }

  test_case->observed_size = attr_size;
  if (test_case->print_bounds) {
    printf("stack_case label=%s requested=%zu actual=%zu low=%p high=%p guard=%zu tid=%lu\n",
           label,
           test_case->requested_size,
           attr_size,
           (void*)low,
           (void*)high,
           guard_size,
           GetCurrentThreadId());
  }
  return test_case->failures == 0;
}

static void* PthreadWorker(void* arg) {
  thread_case_t* test_case = (thread_case_t*)arg;
  ValidateCurrentStack(test_case, "pthread");
  if (test_case->entered != NULL) SetEvent(test_case->entered);
  if (test_case->release != NULL &&
      WaitForSingleObject(test_case->release, INFINITE) != WAIT_OBJECT_0) {
    CaseFail(test_case, "release wait failed");
  }
  return test_case->expected_result;
}

static DWORD WINAPI ExternalWorker(void* arg) {
  thread_case_t* test_case = (thread_case_t*)arg;
  ValidateCurrentStack(test_case, "CreateThread");
  return test_case->failures == 0 ? 0x51a7U : 0U;
}

static DWORD WINAPI FiberWorker(void* arg) {
  thread_case_t* test_case = (thread_case_t*)arg;
  pthread_t self = pthread_self();
  if (self == NULL) {
    CaseFail(test_case, "fiber test could not acquire pthread identity");
    return 1;
  }
  void* fiber = ConvertThreadToFiber(NULL);
  if (fiber == NULL) {
    DWORD error = GetLastError();
    if (error == ERROR_CALL_NOT_IMPLEMENTED) {
      puts("fiber_case skipped=ERROR_CALL_NOT_IMPLEMENTED");
      return 0;
    }
    CaseFail(test_case, "ConvertThreadToFiber failed");
    return 1;
  }
  pthread_attr_t attr;
  if (pthread_getattr_np(self, &attr) != ENOTSUP) {
    CaseFail(test_case, "pthread_getattr_np accepted an active fiber");
  }
  if (!ConvertFiberToThread()) {
    CaseFail(test_case, "ConvertFiberToThread failed");
  }
  puts("fiber_case rejected=1");
  return test_case->failures == 0 ? 0 : 1;
}

static int CheckRequestedReservation(size_t requested_size) {
  thread_case_t test_case;
  memset(&test_case, 0, sizeof(test_case));
  test_case.requested_size = requested_size;
  test_case.expected_result = &test_case;
  test_case.print_bounds = 1;

  pthread_attr_t attr;
  pthread_attr_t* attr_ptr = NULL;
  if (requested_size != 0) {
    if (pthread_attr_init(&attr) != 0 ||
        pthread_attr_setstacksize(&attr, requested_size) != 0) {
      Fail("reservation", "could not prepare stack-size attribute");
      return 0;
    }
    attr_ptr = &attr;
  }

  pthread_t thread = NULL;
  if (pthread_create(&thread, attr_ptr, PthreadWorker, &test_case) != 0 || thread == NULL) {
    Fail("reservation", "pthread_create failed");
    return 0;
  }
  if (attr_ptr != NULL && pthread_attr_destroy(attr_ptr) != 0) {
    Fail("reservation", "pthread_attr_destroy failed");
  }
  void* result = NULL;
  if (pthread_join(thread, &result) != 0 || result != test_case.expected_result) {
    Fail("reservation", "pthread_join did not publish the callback result");
  }

  SYSTEM_INFO system_info;
  GetSystemInfo(&system_info);
  if (requested_size == 0) {
    if (test_case.observed_size < PTHREAD_STACK_MIN) {
      Fail("reservation", "default reservation is too small");
    }
    g_default_stack_size = test_case.observed_size;
  } else {
    const size_t effective_request =
        requested_size < g_default_stack_size ? g_default_stack_size : requested_size;
    if (test_case.observed_size < effective_request ||
        test_case.observed_size - effective_request >=
                 (size_t)system_info.dwAllocationGranularity) {
      Fail("reservation", "effective reservation was not allocation-granularity rounded");
    }
  }
  return test_case.failures == 0;
}

static void CheckAttributeRejections(void) {
  pthread_attr_t attr;
  if (pthread_attr_init(&attr) != 0) {
    Fail("attributes", "pthread_attr_init failed");
    return;
  }
  if (pthread_attr_setstacksize(&attr, PTHREAD_STACK_MIN - 1) != EINVAL) {
    Fail("attributes", "undersized reservation was accepted");
  }
  if (pthread_attr_setdetachstate(&attr, 99) != EINVAL) {
    Fail("attributes", "invalid detach state was accepted");
  }
  char fake_stack = 0;
  if (pthread_attr_setstack(&attr, &fake_stack, 1024 * 1024) != ENOTSUP) {
    Fail("attributes", "custom stack address was accepted");
  }

  thread_case_t test_case;
  memset(&test_case, 0, sizeof(test_case));
  test_case.expected_result = &test_case;
  pthread_t thread = (pthread_t)(uintptr_t)1;
  attr.stackaddr = &fake_stack;
  attr.stacksize = 1024 * 1024;
  if (pthread_create(&thread, &attr, PthreadWorker, &test_case) != ENOTSUP || thread != NULL) {
    Fail("attributes", "pthread_create accepted a custom stack");
  }
  attr.stackaddr = NULL;
  attr.stacksize = PTHREAD_STACK_MIN - 1;
  if (pthread_create(&thread, &attr, PthreadWorker, &test_case) != EINVAL || thread != NULL) {
    Fail("attributes", "pthread_create accepted an invalid stack size");
  }
  if (pthread_attr_destroy(&attr) != 0) {
    Fail("attributes", "pthread_attr_destroy failed");
  }
  if (pthread_create(NULL, NULL, PthreadWorker, &test_case) != EINVAL) {
    Fail("attributes", "pthread_create accepted a null output pointer");
  }
  if (pthread_create(&thread, NULL, NULL, &test_case) != EINVAL || thread != NULL) {
    Fail("attributes", "pthread_create accepted a null callback");
  }
}

static void CheckLiveOtherThread(void) {
  thread_case_t test_case;
  memset(&test_case, 0, sizeof(test_case));
  test_case.entered = CreateEventW(NULL, TRUE, FALSE, NULL);
  test_case.release = CreateEventW(NULL, TRUE, FALSE, NULL);
  test_case.expected_result = &test_case;
  pthread_t thread = NULL;
  if (test_case.entered == NULL || test_case.release == NULL ||
      pthread_create(&thread, NULL, PthreadWorker, &test_case) != 0) {
    Fail("other-thread", "setup failed");
    return;
  }
  WaitForSingleObject(test_case.entered, INFINITE);
  pthread_attr_t attr;
  if (pthread_getattr_np(thread, &attr) != ENOTSUP) {
    Fail("other-thread", "pthread_getattr_np inspected a non-current thread");
  }
  SetEvent(test_case.release);
  if (pthread_join(thread, NULL) != 0) {
    Fail("other-thread", "join failed");
  }
  CloseHandle(test_case.release);
  CloseHandle(test_case.entered);
}

static void CheckDetach(int detach_before_exit, int detached_attribute) {
  thread_case_t test_case;
  memset(&test_case, 0, sizeof(test_case));
  test_case.entered = CreateEventW(NULL, TRUE, FALSE, NULL);
  test_case.release = CreateEventW(NULL, TRUE, FALSE, NULL);
  test_case.expected_result = &test_case;

  pthread_attr_t attr;
  pthread_attr_t* attr_ptr = NULL;
  if (detached_attribute) {
    pthread_attr_init(&attr);
    pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
    attr_ptr = &attr;
  }

  pthread_t thread = NULL;
  if (test_case.entered == NULL || test_case.release == NULL ||
      pthread_create(&thread, attr_ptr, PthreadWorker, &test_case) != 0) {
    Fail("detach", "setup failed");
    return;
  }
  if (attr_ptr != NULL) pthread_attr_destroy(attr_ptr);
  WaitForSingleObject(test_case.entered, INFINITE);
  DWORD tid = pthread_gettid_np(thread);
  HANDLE wait_handle = OpenThread(SYNCHRONIZE, FALSE, tid);
  if (wait_handle == NULL) {
    Fail("detach", "could not duplicate synchronization ownership");
  }

  if (detached_attribute) {
    if (pthread_join(thread, NULL) != EINVAL) {
      Fail("detach", "join accepted an attribute-detached thread");
    }
  } else if (detach_before_exit && pthread_detach(thread) != 0) {
    Fail("detach", "detach-before-exit failed");
  }

  SetEvent(test_case.release);
  if (wait_handle != NULL) {
    WaitForSingleObject(wait_handle, INFINITE);
    CloseHandle(wait_handle);
  }
  if (!detached_attribute && !detach_before_exit && pthread_detach(thread) != 0) {
    Fail("detach", "detach-after-exit failed");
  }
  CloseHandle(test_case.release);
  CloseHandle(test_case.entered);
}

static void CheckJoinStress(void) {
  DWORD handles_before = 0;
  DWORD handles_after = 0;
  GetProcessHandleCount(GetCurrentProcess(), &handles_before);
  for (int i = 0; i < kJoinStressCount; ++i) {
    thread_case_t test_case;
    memset(&test_case, 0, sizeof(test_case));
    test_case.expected_result = &test_case;
    pthread_t thread = NULL;
    if (pthread_create(&thread, NULL, PthreadWorker, &test_case) != 0) {
      Fail("join-stress", "pthread_create failed");
      break;
    }
    void* result = NULL;
    if (pthread_join(thread, &result) != 0 || result != &test_case || test_case.failures != 0) {
      Fail("join-stress", "join/result/stack validation failed");
      break;
    }
  }
  GetProcessHandleCount(GetCurrentProcess(), &handles_after);
  if (handles_after > handles_before + 4) {
    Fail("join-stress", "process handle count grew unexpectedly");
  }
  printf("join_stress count=%d handles_before=%lu handles_after=%lu\n",
         kJoinStressCount,
         handles_before,
         handles_after);
}

static void CheckDetachStress(void) {
  for (int i = 0; i < kDetachStressCount; ++i) {
    thread_case_t test_case;
    memset(&test_case, 0, sizeof(test_case));
    test_case.entered = CreateEventW(NULL, TRUE, FALSE, NULL);
    test_case.release = CreateEventW(NULL, TRUE, FALSE, NULL);
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setdetachstate(&attr, PTHREAD_CREATE_DETACHED);
    pthread_t thread = NULL;
    if (pthread_create(&thread, &attr, PthreadWorker, &test_case) != 0) {
      Fail("detach-stress", "pthread_create failed");
      break;
    }
    pthread_attr_destroy(&attr);
    WaitForSingleObject(test_case.entered, INFINITE);
    HANDLE wait_handle = OpenThread(SYNCHRONIZE, FALSE, pthread_gettid_np(thread));
    SetEvent(test_case.release);
    if (wait_handle == NULL || WaitForSingleObject(wait_handle, INFINITE) != WAIT_OBJECT_0) {
      Fail("detach-stress", "thread completion wait failed");
      break;
    }
    CloseHandle(wait_handle);
    CloseHandle(test_case.release);
    CloseHandle(test_case.entered);
    if (test_case.failures != 0) {
      Fail("detach-stress", "stack validation failed");
      break;
    }
  }
  printf("detach_stress count=%d\n", kDetachStressCount);
}

static void CheckExternalAndFiberThreads(void) {
  thread_case_t external_case;
  memset(&external_case, 0, sizeof(external_case));
  external_case.print_bounds = 1;
  HANDLE thread = CreateThread(NULL, 0, ExternalWorker, &external_case, 0, NULL);
  DWORD exit_code = 0;
  if (thread == NULL || WaitForSingleObject(thread, INFINITE) != WAIT_OBJECT_0 ||
      !GetExitCodeThread(thread, &exit_code) || exit_code != 0x51a7U ||
      external_case.failures != 0) {
    Fail("CreateThread", "external pthread identity or bounds failed");
  }
  if (thread != NULL) CloseHandle(thread);

  thread_case_t fiber_case;
  memset(&fiber_case, 0, sizeof(fiber_case));
  thread = CreateThread(NULL, 0, FiberWorker, &fiber_case, 0, NULL);
  exit_code = 1;
  if (thread == NULL || WaitForSingleObject(thread, INFINITE) != WAIT_OBJECT_0 ||
      !GetExitCodeThread(thread, &exit_code) || exit_code != 0 ||
      fiber_case.failures != 0) {
    Fail("fiber", "fiber rejection test failed");
  }
  if (thread != NULL) CloseHandle(thread);
}

int main(void) {
  thread_case_t main_case;
  memset(&main_case, 0, sizeof(main_case));
  main_case.print_bounds = 1;
  ValidateCurrentStack(&main_case, "main");

  pthread_t self = pthread_self();
  if (pthread_join(self, NULL) != EDEADLK) {
    Fail("identity", "self join did not return EDEADLK");
  }
  if (pthread_detach(self) != EINVAL) {
    Fail("identity", "external identity detach did not return EINVAL");
  }
  if (pthread_join(NULL, NULL) != ESRCH || pthread_detach(NULL) != ESRCH ||
      pthread_kill(NULL, 0) != ESRCH || pthread_kill(self, 0) != 0) {
    Fail("identity", "null/external identity errors are inconsistent");
  }

  CheckAttributeRejections();
  CheckRequestedReservation(0);
  CheckRequestedReservation(64 * 1024);
  CheckRequestedReservation(256 * 1024);
  CheckRequestedReservation(1024 * 1024);
  CheckRequestedReservation(2 * 1024 * 1024);
  CheckRequestedReservation(9 * 1024 * 1024);
  CheckLiveOtherThread();
  CheckDetach(1, 0);
  CheckDetach(0, 0);
  CheckDetach(0, 1);
  CheckJoinStress();
  CheckDetachStress();
  CheckExternalAndFiberThreads();

  printf("win32_thread_stack_probe failures=%ld join_stress=%d detach_stress=%d\n",
         g_failures,
         kJoinStressCount,
         kDetachStressCount);
  if (g_failures != 0) return 1;
  puts("win32_thread_stack_probe OK");
  return 0;
}
