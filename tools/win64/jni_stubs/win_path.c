#include "win_path.h"
#include <stdlib.h>
#include <string.h>
#include <ctype.h>
#include <windows.h>

static int is_sep(unsigned char c) { return c == '/' || c == '\\'; }

int win_path_normalize(const char* in, char* out, size_t out_cap) {
  if (!in || !out || out_cap == 0) return -1;
  size_t n = strlen(in);
  if (n == 0) {
    if (out_cap < 1) return -1;
    out[0] = 0;
    return 0;
  }

  char* tmp = (char*)malloc(n + 4);
  if (!tmp) return -1;
  size_t j = 0;
  int prev_sep = 0;
  for (size_t i = 0; i < n; i++) {
    unsigned char c = (unsigned char)in[i];
    if (is_sep(c)) {
      if (prev_sep) continue;
      tmp[j++] = '\\';
      prev_sep = 1;
    } else {
      tmp[j++] = (char)c;
      prev_sep = 0;
    }
  }
  if (j > 1 && tmp[j - 1] == '\\') {
    int is_drive_root = (j == 3 && isalpha((unsigned char)tmp[0]) && tmp[1] == ':');
    if (!is_drive_root) j--;
  }
  if (j == 2 && isalpha((unsigned char)tmp[0]) && tmp[1] == ':') {
    tmp[j++] = '\\';
  }
  tmp[j] = 0;

  size_t prefix = 0;
  if (j >= 2 && tmp[1] == ':' && isalpha((unsigned char)tmp[0])) {
    prefix = (j >= 3 && tmp[2] == '\\') ? 3 : 2;
  } else if (j >= 2 && tmp[0] == '\\' && tmp[1] == '\\') {
    prefix = 2;
    int segs = 0;
    for (size_t i = 2; i < j; i++) {
      if (tmp[i] == '\\') {
        segs++;
        if (segs == 2) { prefix = i + 1; break; }
      }
    }
  } else if (j >= 1 && tmp[0] == '\\') {
    prefix = 1;
  }

  char* stack[256];
  int np = 0;
  size_t i = prefix;
  while (i <= j) {
    size_t start = i;
    while (i < j && tmp[i] != '\\') i++;
    size_t len = i - start;
    if (len == 0) {
      /* skip empty */
    } else if (len == 1 && tmp[start] == '.') {
      /* skip . */
    } else if (len == 2 && tmp[start] == '.' && tmp[start + 1] == '.') {
      if (np > 0) {
        free(stack[--np]);
      } else if (prefix == 0) {
        if (np >= 256) { free(tmp); return -1; }
        char* seg = (char*)malloc(3);
        if (!seg) { free(tmp); return -1; }
        seg[0] = seg[1] = '.'; seg[2] = 0;
        stack[np++] = seg;
      }
    } else {
      if (np >= 256) {
        for (int k = 0; k < np; k++) free(stack[k]);
        free(tmp);
        return -1;
      }
      char* seg = (char*)malloc(len + 1);
      if (!seg) {
        for (int k = 0; k < np; k++) free(stack[k]);
        free(tmp);
        return -1;
      }
      memcpy(seg, tmp + start, len);
      seg[len] = 0;
      stack[np++] = seg;
    }
    if (i >= j) break;
    i++;
  }

  size_t o = 0;
  if (prefix > 0) {
    if (o + prefix >= out_cap) goto oom;
    memcpy(out + o, tmp, prefix);
    o += prefix;
  }
  for (int s = 0; s < np; s++) {
    size_t pl = strlen(stack[s]);
    if (o > 0 && out[o - 1] != '\\') {
      if (o + 1 >= out_cap) goto oom;
      out[o++] = '\\';
    }
    if (o + pl >= out_cap) goto oom;
    memcpy(out + o, stack[s], pl);
    o += pl;
    free(stack[s]);
    stack[s] = NULL;
  }
  if (o == 2 && out[1] == ':') {
    if (o + 1 >= out_cap) goto oom;
    out[o++] = '\\';
  }
  if (o == 0) {
    if (out_cap < 2) goto oom;
    out[0] = '.';
    out[1] = 0;
    free(tmp);
    return 0;
  }
  out[o] = 0;
  free(tmp);
  return 0;

oom:
  for (int s = 0; s < np; s++) if (stack[s]) free(stack[s]);
  free(tmp);
  return -1;
}

wchar_t* win_path_to_wide(const char* utf8_path) {
  if (!utf8_path) return NULL;
  char norm[4096];
  if (win_path_normalize(utf8_path, norm, sizeof(norm)) != 0) return NULL;
  int wlen = MultiByteToWideChar(CP_UTF8, 0, norm, -1, NULL, 0);
  if (wlen <= 0) wlen = MultiByteToWideChar(CP_ACP, 0, norm, -1, NULL, 0);
  if (wlen <= 0) return NULL;
  wchar_t* w = (wchar_t*)malloc((size_t)wlen * sizeof(wchar_t));
  if (!w) return NULL;
  if (!MultiByteToWideChar(CP_UTF8, 0, norm, -1, w, wlen)) {
    MultiByteToWideChar(CP_ACP, 0, norm, -1, w, wlen);
  }
  return w;
}
