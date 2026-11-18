#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <subhook.h>

typedef void (*foo_func_t)(void);

#ifdef SUBHOOK_X86
  #if defined SUBHOOK_WINDOWS
    #define FOO_CALL __cdecl
  #elif defined SUBHOOK_UNIX
    #define FOO_CALL __attribute__((cdecl))
  #endif
#endif
#ifndef FOO_CALL
  #define FOO_CALL
#endif

extern void FOO_CALL foo(void);
foo_func_t foo_tr = NULL;

void foo_hooked(void) {
  puts("foo_hooked() called");
}

void foo_hooked_tr(void) {
  puts("foo_hooked_tr() called");
  foo_tr();
}

#if defined(SUBHOOK_X86_64) && defined(SUBHOOK_UNIX)
typedef int (FOO_CALL *foo_frame_func_t)(void);
extern int FOO_CALL foo_frame(void);
static foo_frame_func_t foo_frame_tr = NULL;
static int foo_frame_result = 0;

static void foo_frame_hooked(void) {
  foo_frame_result = foo_frame_tr();
}
#endif

int main() {
  puts("Testing initial install");

  subhook_t foo_hook = subhook_new((void *)foo,
                                   (void *)foo_hooked,
                                   SUBHOOK_64BIT_OFFSET);
  if (foo_hook == NULL || subhook_install(foo_hook) < 0) {
    puts("Install failed");
    return EXIT_FAILURE;
  }
  foo();
  if (subhook_remove(foo_hook) < 0) {
    puts("Remove failed");
    return EXIT_FAILURE;
  }
  foo();

  puts("Testing re-install");

  if (subhook_install(foo_hook) < 0) {
    puts("Install failed");
    return EXIT_FAILURE;
  }
  foo();
  if (subhook_remove(foo_hook) < 0) {
    puts("Remove failed");
    return EXIT_FAILURE;
  }
  foo();

  puts("Testing trampoline");

  subhook_t foo_hook_tr = subhook_new((void *)foo,
                                      (void *)foo_hooked_tr,
                                      SUBHOOK_64BIT_OFFSET);
  if (subhook_install(foo_hook_tr) < 0) {
    puts("Install failed");
    return EXIT_FAILURE;
  }
  foo_tr = (foo_func_t)subhook_get_trampoline(foo_hook_tr);
  if (foo_tr == NULL) {
    puts("Failed to build trampoline");
    return EXIT_FAILURE;
  }
  foo();

#if defined(SUBHOOK_X86_64) && defined(SUBHOOK_UNIX)
  puts("Testing stack-relative displacement trampoline");
  if (foo_frame() != 42) {
    puts("Unhooked function returned an unexpected value");
    return EXIT_FAILURE;
  }

  subhook_t foo_frame_hook = subhook_new((void *)foo_frame,
                                         (void *)foo_frame_hooked,
                                         SUBHOOK_64BIT_OFFSET);
  if (foo_frame_hook == NULL || subhook_install(foo_frame_hook) < 0) {
    puts("Frame hook install failed");
    return EXIT_FAILURE;
  }
  foo_frame_tr = (foo_frame_func_t)subhook_get_trampoline(foo_frame_hook);
  if (foo_frame_tr == NULL) {
    puts("Failed to build frame trampoline");
    return EXIT_FAILURE;
  }
  foo_frame();
  if (foo_frame_result != 42) {
    puts("Frame trampoline returned an unexpected value");
    return EXIT_FAILURE;
  }
  if (subhook_remove(foo_frame_hook) < 0) {
    puts("Frame hook remove failed");
    return EXIT_FAILURE;
  }
#endif

  return EXIT_SUCCESS;
}
