// paths are relative to the build dir

#include "../cdefs/internals.h"
#include "../cdefs/generated.h" // needed to define enum values
#include "../cdefs/XDL.h"

#include "../libs/subhook/subhook.h"
#include "../libs/plthook/plthook.h"

#include <SDL2/SDL.h>

#include <dlfcn.h>

uint32_t kickstart(void);

CFFI_DLLEXPORT int SDL_Init(uint32_t flags) {
	kickstart();
	return ((int(*)(uint32_t))dlsym(RTLD_NEXT, "SDL_Init"))(flags);
}
