#include <pthread.h>
#include <windows.h>

#include <stdio.h>

enum {
  kThreadCount = 32,
  kExpectedValue = 0x12345678,
};

static pthread_once_t g_once = PTHREAD_ONCE_INIT;
static HANDLE g_start_event;
static volatile LONG g_init_calls;
static volatile LONG g_failures;
static volatile LONG g_value;

static void InitializeValue(void) {
  InterlockedIncrement(&g_init_calls);
  Sleep(100);
  InterlockedExchange(&g_value, kExpectedValue);
}

static DWORD WINAPI RunOnce(void* arg) {
  (void)arg;
  WaitForSingleObject(g_start_event, INFINITE);
  pthread_once(&g_once, InitializeValue);
  if (InterlockedCompareExchange(&g_value, 0, 0) != kExpectedValue) {
    InterlockedIncrement(&g_failures);
  }
  return 0;
}

int main(void) {
  HANDLE threads[kThreadCount];
  g_start_event = CreateEventW(NULL, TRUE, FALSE, NULL);
  if (g_start_event == NULL) {
    fprintf(stderr, "CreateEventW failed: %lu\n", GetLastError());
    return 1;
  }

  for (int i = 0; i < kThreadCount; ++i) {
    threads[i] = CreateThread(NULL, 0, RunOnce, NULL, 0, NULL);
    if (threads[i] == NULL) {
      fprintf(stderr, "CreateThread failed at %d: %lu\n", i, GetLastError());
      return 1;
    }
  }

  SetEvent(g_start_event);
  DWORD wait_result = WaitForMultipleObjects(kThreadCount, threads, TRUE, INFINITE);
  if (wait_result == WAIT_FAILED) {
    fprintf(stderr, "WaitForMultipleObjects failed: %lu\n", GetLastError());
    return 1;
  }

  for (int i = 0; i < kThreadCount; ++i) {
    CloseHandle(threads[i]);
  }
  CloseHandle(g_start_event);

  printf("pthread_once_probe init_calls=%ld failures=%ld value=0x%08lx\n",
         g_init_calls,
         g_failures,
         g_value);
  if (g_init_calls != 1 || g_failures != 0 || g_value != kExpectedValue) {
    return 1;
  }
  puts("pthread_once_probe OK");
  return 0;
}
