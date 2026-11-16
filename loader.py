import configparser
import json
import os
import platform
import shutil
import subprocess
import sys
import sysconfig
import time

import logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

if platform.system() != 'Linux':
    raise RuntimeError('SBPE supports Linux only')


def default_game_path():
    steam_dirs = (
        '~/.steam/steam',
        '~/.local/share/Steam',
        '~/.var/app/com.valvesoftware.Steam/.local/share/Steam',
    )
    candidates = [
        os.path.join(os.path.expanduser(root), 'steamapps', 'common',
                     'StarBreak', 'mvmmoclient')
        for root in steam_dirs
    ]
    return next((path for path in candidates if os.path.isfile(path)),
                candidates[0])


DEFAULTGAMEPATH = default_game_path()

SCRIPTPATH = os.path.dirname(os.path.abspath(__file__))
REMOTEFILE = 'remote.so'
REMOTEPATH = os.path.normpath(os.path.join(SCRIPTPATH, 'build', REMOTEFILE))
CONFFILE = os.path.join(SCRIPTPATH, 'config.ini')
CONF_TEMPLATE = os.path.join(SCRIPTPATH, 'config_template.ini')
SYMFILE = os.path.join(SCRIPTPATH, 'symbols.json')

# offsets of these symbols will be passed to the remote
SYMBOLS = '''
stage window_ canvasW_ canvasH_
mouseMoveCallback mouseButtonCallback windowEventCallback
userData_

XDL_GetWindowSize
XDL_DoEvents XDL_Clear XDL_Present
XDL_DrawPoint XDL_DrawLine XDL_DrawRect XDL_DrawTri XDL_FillRect XDL_FillTri
XDL_LoadTextFile XDL_LoadTextureFile XDL_CreateTextTexture
XDL_CalculateTextWidth XDL_LineSpacing
XDL_QueryTexture XDL_DrawTexture
XDL_GetNumberDict XDL_DrawFromNumberDict XDL_SizeFromNumberDict
XDL_DestroyTexture
XDL_TrackGAEvent

flags::drawHUD
flags::drawTiles
flags::drawEdge
flags::drawScatter
flags::drawUniform
flags::drawHitBoxes
flags::drawBoxes

WorldClient::handleWindowEvent
UIElementContainer::handleWindowEvent
'''.split()

LINUX_SYMBOLS = [
    'ClientWorld::player',
    'ClientWorld::getObjs'
]


def _resolve_linux_symbols(exepath):
    try:
        output = subprocess.check_output(
            ['nm', '-C', '-n', '--defined-only', exepath],
            stderr=subprocess.STDOUT)
    except (OSError, subprocess.CalledProcessError) as error:
        logging.error('failed to read ELF symbols with nm: {}'.format(error))
        return None

    missing = set(SYMBOLS + LINUX_SYMBOLS)
    offsets = {}
    for line in output.decode(errors='replace').splitlines():
        parts = line.split(None, 2)
        if len(parts) != 3:
            continue
        address, _, symbol = parts
        for expected in tuple(missing):
            if symbol == expected or symbol.startswith(expected + '('):
                try:
                    offsets[expected] = int(address, 16)
                except ValueError:
                    logging.error('invalid ELF symbol address for "{}"'.format(expected))
                    return None
                missing.remove(expected)

    if missing:
        logging.error('could not find symbols in ELF: ' + ' '.join(sorted(missing)))
        return None
    return offsets


def resolveSymbols(exepath):
    return _resolve_linux_symbols(exepath)


def launch(exepath):
    preload = [REMOTEPATH]
    game_dir = os.path.dirname(os.path.abspath(exepath))
    common_dir = os.path.dirname(game_dir)
    multiarch = '{}-linux-gnu'.format(platform.machine())
    runtime_dirs = (
        os.path.join(
            common_dir, 'SteamLinuxRuntime', 'steam-runtime', 'lib',
            multiarch),
        os.path.join(
            os.path.expanduser('~/.local/share/Steam'),
            'ubuntu12_32', 'steam-runtime', 'lib', multiarch),
        os.path.join(
            os.path.expanduser('~/.steam/steam'),
            'ubuntu12_32', 'steam-runtime', 'lib', multiarch),
    )
    png_compat = next((
        os.path.join(path, 'libpng12.so.0')
        for path in runtime_dirs
        if os.path.isfile(os.path.join(path, 'libpng12.so.0'))
    ), None)
    if png_compat:
        preload.append(png_compat)
        logging.info('using Steam runtime PNG compatibility library')
    else:
        logging.warning(
            'Steam runtime libpng12.so.0 not found; the game may fail '
            'to initialize PNG support')

    preload.extend(os.environ.get('LD_PRELOAD', '').split())
    os.environ['LD_PRELOAD'] = ' '.join(preload)
    os.environ['SBPE_SITEPACKAGES'] = sysconfig.get_path('purelib')

    # start the game
    return subprocess.Popen(
        [exepath], stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE, cwd=os.path.dirname(exepath))


def runLoader(exepath=''):
    mipmaps = False

    # ensure config exists
    if not os.path.exists(CONFFILE):
        logging.info('config not found, copying from template')
        try:
            shutil.copy(CONF_TEMPLATE, CONFFILE)
        except Exception:
            logging.error('failed to copy config!')
            return False

    conf = configparser.ConfigParser()
    conf.read(CONFFILE)
    configured_game = conf.get('general', 'game', fallback='').strip()
    if configured_game:
        exepath = configured_game
    else:
        exepath = exepath or DEFAULTGAMEPATH
    mipmaps = conf.getboolean('general', 'mipmaps', fallback=False)
    keepopen = conf.getboolean('general', 'keep_open', fallback=False)

    if not os.path.isfile(REMOTEPATH):
        logging.error('missing native helper: {}'.format(REMOTEPATH))
        logging.error('build the Linux shared library as {}'.format(REMOTEPATH))
        return False

    # ensure the binary exists
    if not os.path.isfile(exepath):
        logging.error('put the path to the game executable in ' + CONFFILE)
        return False

    # resolve symbols and prepare environment
    offsets = resolveSymbols(exepath)
    if offsets is not None:
        logging.info('symbols ok')
    else:
        logging.error('symbols not ok')
        return False

    with open(SYMFILE, 'wb') as f:
        f.write(json.dumps(offsets).encode('utf-8'))

    os.environ['SBPE_SYMFILE'] = SYMFILE

    # texture dir and dataVersion paths
    gdir = os.path.dirname(os.path.abspath(exepath))
    tdir = os.path.join(gdir, 'data', 'texture')

    dvpath = os.path.join(tdir, 'dataVersion.bpb')
    dvmpath = os.path.join(tdir, 'dataVersion.m.bpb')
    dvbak = os.path.join(tdir, 'dataVersion.bpb.bak')

    if not os.path.exists(dvbak):
        # create a backup of the original file if there is none
        shutil.copy(dvpath, dvbak)
    else:
        # otherwise restore from backup to reset state
        shutil.copy(dvbak, dvpath)

    # generate mipmaps if needed
    if mipmaps:
        logging.info('checking mipmaps...')

        try:
            import genmipmaps
        except ModuleNotFoundError as error:
            if error.name in (
                    'PIL', 'google', 'google.protobuf', '_cffi_backend'):
                logging.error(
                    'missing Python dependency "{}"; install Linux runtime '
                    'requirements with: python3 -m pip install -r '
                    'requirements-linux.txt'.format(error.name))
                return False
            raise
        genmipmaps.BASEPATH = tdir
        mn = conf.getint('general', 'mipmap_maxlevel', fallback=2)
        genmipmaps.main(tdir, mipmaps=mn)

    # overwrite dataVersion
    if mipmaps:
        shutil.copy(dvmpath, dvpath)

    # remove old log
    rlog = None
    rlogpath = os.path.join(SCRIPTPATH, 'remote.log')
    if os.path.exists(rlogpath):
        os.unlink(rlogpath)

    # start the game
    gpop = launch(exepath)

    if not gpop:
        logging.error('failed to launch')
        return False

    logging.info('game pid {}'.format(gpop.pid))

    # exit here to close the console window
    if not keepopen:
        return True

    # mirror log
    while not os.path.exists(rlogpath) and gpop.poll() is None:
        logging.info('waiting for log')
        time.sleep(0.5)

    if os.path.exists(rlogpath):
        rlog = open(rlogpath, 'r')
        logging.info('following remote.log...')

    try:
        while gpop.poll() is None:
            while rlog is not None:
                s = rlog.read()
                if len(s) == 0:
                    break
                sys.stdout.write(s)
            time.sleep(0.5)
    except Exception:
        gpop.kill()

    logging.info('game closed: code {}'.format(gpop.returncode))

    # dump stdout
    stdo = gpop.communicate()[0].decode()

    if len(stdo) > 0:
        logging.info('stdout:')
        print(stdo)

    return True


if __name__ == '__main__':
    logging.info('SBPE loader')
    if runLoader(DEFAULTGAMEPATH) is False:
        input('\npress ENTER to exit')
