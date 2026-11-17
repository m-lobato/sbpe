import sys

import cffi


if sys.platform != 'linux':
    raise RuntimeError('SBPE native helper can only be built on Linux')

LIB_BASE = '../libs/'
EXTRA_SRC = [LIB_BASE + 'subhook/subhook.c']
CDEFS = 'generated internals SDL XDL subhook xternPython'.split()
TARGET = 'remote.so'
LIBRARIES = ['SDL2', 'dl']


def readfile(path):
    with open(path, 'r') as source:
        return source.read()


def build():
    ffibuilder = cffi.FFI()

    for name in CDEFS:
        ffibuilder.cdef(readfile('cdefs/{}.h'.format(name)))

    ffibuilder.embedding_api('uint32_t kickstart();')
    ffibuilder.embedding_init_code(readfile('remote.py'))
    ffibuilder.set_source(
        '_remote',
        readfile('cdefs/remote.c'),
        sources=EXTRA_SRC,
        libraries=LIBRARIES,
        define_macros=[('SUBHOOK_STATIC', None)],
        extra_compile_args=['-std=gnu17'])
    ffibuilder.compile(tmpdir='build', target=TARGET)


if __name__ == '__main__':
    build()
