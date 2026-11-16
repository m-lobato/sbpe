import configparser
import ctypes
import importlib
import json
import logging
import os
import platform
import queue
import sys
import time

from _remote import ffi, lib

util = None

VERSION = 'v1.7.0'
LOGFILE = 'remote.log'
CONFIGFILE = 'config.ini'

# non-function imported symbol types
SYMTYPES = {
    'stage': 'struct Stage **',
    'window_': 'void **',
    'canvasW_': 'int *',
    'canvasH_': 'int *',
    'userData_': 'void **',
    'WorldClient::handleWindowEvent': 'void *',
    'UIElementContainer::handleWindowEvent': 'void *'
}


class dotdict(dict):
    '''dict with dot notation accessors'''
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


# various references to pass around (symbols, constants, etc)
refs = dotdict(
    tops=[],  # collection of direct children of stage
    topTypes=[],  # the class names of tops
    MainMenu=ffi.NULL,
    GameClient=ffi.NULL,
    WorldClient=ffi.NULL,
    ClientWorld=ffi.NULL,
    WorldView=ffi.NULL,
    overrideW=0, overrideH=0,  # fake values to return from XDL_GetWindowSize
    windowW=0, windowH=0,  # current window size
    scaleX=1, scaleY=1,    # current window scale
    lastMove=0  # timestamp of last mouse movement
)

refs.VERSION = VERSION
refs.SYSINFO = '{0} v{1} {2} @ {3}'.format(
    platform.python_implementation(), platform.python_version(),
    platform.architecture()[0], platform.platform())

refs.config = configparser.ConfigParser()
refs.config.optionxform = str

refs.manager = None


def _main_executable_load_bias():
    class DlPhdrInfo(ctypes.Structure):
        _fields_ = [
            ('addr', ctypes.c_void_p),
            ('name', ctypes.c_char_p),
            ('phdr', ctypes.c_void_p),
            ('phnum', ctypes.c_ushort),
        ]

    callback_type = ctypes.CFUNCTYPE(
        ctypes.c_int, ctypes.POINTER(DlPhdrInfo), ctypes.c_size_t,
        ctypes.c_void_p)
    load_bias = []

    @callback_type
    def find_main_executable(info, size, data):
        if not info.contents.name:
            load_bias.append(info.contents.addr or 0)
            return 1
        return 0

    libc = ctypes.CDLL(None)
    iterate_phdr = libc.dl_iterate_phdr
    iterate_phdr.argtypes = [callback_type, ctypes.c_void_p]
    iterate_phdr.restype = ctypes.c_int
    iterate_phdr(find_main_executable, None)
    if not load_bias:
        raise RuntimeError('could not determine the main executable load address')
    return load_bias[0]


# hooks ######################################################################

ORIGS = {}
_pending_mipmaps = queue.SimpleQueue()
# C callbacks may still be executing on worker threads after notifying Python.
_texture_callbacks = []


@ffi.def_extern()
def hook_DoEvents():
    refs.manager.run()
    refs.manager.runCallbacks('beforeUpdate')
    ORIGS['XDL_DoEvents']()
    while True:
        try:
            texture, pname, sheet = _pending_mipmaps.get_nowait()
        except queue.Empty:
            break
        if os.environ.get('SBPE_TRACE_MIPMAPS') == '1':
            logging.info(
                'mipmap upload start %s sheet %s texture %s',
                pname, sheet, texture)
        util.loadMipmaps(pname, sheet, texture)
        if os.environ.get('SBPE_TRACE_MIPMAPS') == '1':
            logging.info(
                'mipmap upload end %s sheet %s texture %s',
                pname, sheet, texture)
@ffi.def_extern()
def hook_Clear(color):
    util.updateState()
    refs.manager.runCallbacks('afterUpdate')
    ORIGS['XDL_Clear'](refs.stage[0].backgroundColor)


@ffi.def_extern()
def hook_Present():
    refs.manager.runCallbacks('onPresent')
    ORIGS['XDL_Present']()


@ffi.def_extern()
def hook_GetWindowSize(wptr, hptr):
    if refs.overrideW > 0:
        wptr[0] = refs.overrideW
        hptr[0] = refs.overrideH
    else:
        lib.SDL_GetWindowSize(refs.window_[0], wptr, hptr)


@ffi.def_extern()
def hook_TrackGAEvent(category, action, label, value):
    pass
    # logging.debug('GA: {}.{} "{}" {}'.format(
    #     ffi.string(category).decode(), ffi.string(action).decode(),
    #     ffi.string(label).decode(), value))


@ffi.def_extern()
def hook_mouseMove(x, y, userData):
    x = round(x * refs.scaleX)
    y = round(y * refs.scaleY)
    ORIGS['mouseMoveCallback'](x, y, userData)
    refs.lastMove = time.perf_counter()


@ffi.def_extern()
def hook_mouseButton(x, y, button, down, userData):
    x = round(x * refs.scaleX)
    y = round(y * refs.scaleY)
    ORIGS['mouseButtonCallback'](x, y, button, down, userData)


@ffi.def_extern()
def hook_LoadTextureFile(name, callback, userData):
    texture_name = ffi.string(name).decode()
    original_callback = ffi.cast('XDL_LoadTextureDoneCallback', callback)

    def texture_callback(texture, sheet_ptr):
        original_callback(texture, sheet_ptr)
        path = texture_name.split('/')
        if len(path) < 2 or path[0] != 'texture':
            return
        pname, sid = path[1].split('.', 1)
        sid = sid.split('.')
        if sid[0] == 'm0':
            _pending_mipmaps.put((texture, pname, sid[1]))

    callback_proxy = ffi.callback(
        'XDL_LoadTextureDoneCallback', texture_callback)
    ORIGS['XDL_LoadTextureFile'](name, callback_proxy, userData)
    _texture_callbacks.append(callback_proxy)


def initHooks():
    def addhook(fname, hookfunc, ret=False):
        hook = lib.subhook_new(refs[fname], hookfunc, 1)
        orig = ffi.cast('p' + fname, lib.subhook_get_trampoline(hook))
        if fname == 'XDL_LoadTextureFile':
            orig = ffi.NULL
        if orig != ffi.NULL:
            ORIGS[fname] = orig
        else:
            logging.info('{}: no trampoline, using fallback'.format(fname))

            def call_orig(*args):
                if lib.subhook_remove(hook) < 0:
                    logging.error('failed to remove hook {}'.format(fname))
                    return
                try:
                    res = refs[fname](*args)
                finally:
                    if lib.subhook_install(hook) < 0:
                        logging.error('failed to reinstall hook {}'.format(fname))
                if ret:
                    return res

            ORIGS[fname] = call_orig

        lib.subhook_install(hook)
        if not lib.subhook_is_installed(hook):
            logging.error('failed to hook {}'.format(fname))

    addhook('XDL_DoEvents', lib.hook_DoEvents)
    addhook('XDL_Clear', lib.hook_Clear)
    addhook('XDL_Present', lib.hook_Present)
    addhook('XDL_GetWindowSize', lib.hook_GetWindowSize)
    addhook('XDL_TrackGAEvent', lib.hook_TrackGAEvent)
    addhook('mouseMoveCallback', lib.hook_mouseMove)
    addhook('mouseButtonCallback', lib.hook_mouseButton)

    if refs.config.getboolean('general', 'mipmaps', fallback=False):
        addhook('XDL_LoadTextureFile', lib.hook_LoadTextureFile)


# startup ####################################################################

@ffi.def_extern()
def kickstart():
    global refs, util

    SYMFILE = os.environ['SBPE_SYMFILE']

    with open(SYMFILE, 'rb') as f:
        offsets = json.loads(f.read().decode('utf-8'))

    load_bias = _main_executable_load_bias()
    offsets = {name: address + load_bias
               for name, address in offsets.items()}

    refs.SCRIPTPATH = os.path.dirname(SYMFILE)
    sys.path.insert(1, refs.SCRIPTPATH)
    site_packages = os.environ.get('SBPE_SITEPACKAGES')
    if site_packages and os.path.isdir(site_packages):
        sys.path.insert(1, site_packages)

    logging.basicConfig(
        level=logging.INFO,
        filename=os.path.join(refs.SCRIPTPATH, LOGFILE), filemode='w',
        format='%(asctime)s %(module)s [%(levelname)s] %(message)s')

    logging.info('SBPE ' + refs.VERSION)
    logging.info('platform: ' + refs.SYSINFO)

    refs.CONFIGFILE = os.path.join(refs.SCRIPTPATH, CONFIGFILE)
    refs.config.read(refs.CONFIGFILE)

    # import native functions/objects
    for sname in offsets:
        offset = offsets[sname]
        if sname in SYMTYPES:
            # objects, variables
            refs[sname] = ffi.cast(SYMTYPES[sname], offset)
        elif sname == 'ClientWorld::player':
            refs.ClientWorld_player = ffi.cast(
                'struct Player *(*)(void *)', offset)
        elif sname == 'ClientWorld::getObjs':
            refs.ClientWorld_getObjs = ffi.cast(
                'void (*)(void *, struct STDVector *)', offset)
        elif sname.startswith('flags::'):
            # flags
            refs[sname[7:]] = ffi.cast('uint8_t *', offset)
        else:
            # functions
            refs[sname] = ffi.cast('p' + sname, offset)

    # import object inheritance info
    with open(os.path.join(refs.SCRIPTPATH, 'cdefs/proto.json'), 'r') as f:
        d = json.load(f)
        refs.CHAINS = d['chains']
        refs.CASTABLE = d['castable']

    # import util
    util = importlib.import_module('util')
    util.refs = refs

    # import plugins
    plugpath = os.path.join(refs.SCRIPTPATH, 'plugins')
    man = importlib.import_module('manager')
    refs.manager = man.Manager(path=plugpath, refs=refs)

    # init hooks
    initHooks()

    logging.info('startup ok')
    return 0
