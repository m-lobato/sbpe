#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON=${PYTHON:-python3}
VENV="$ROOT/.venv"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    printf 'Python interpreter not found: %s\n' "$PYTHON" >&2
    exit 1
fi

"$PYTHON" -c '
import platform
import sys
if sys.platform != "linux":
    raise SystemExit("SBPE Linux build must run on Linux")
if sys.version_info[:2] != (3, 13):
    raise SystemExit(
        "SBPE Linux build currently targets Python 3.13; found "
        + sys.version.split()[0]
    )
if platform.machine() != "x86_64":
    raise SystemExit(
        "SBPE Linux build currently targets x86_64; found "
        + platform.machine()
    )
'

for tool in cc c++ nm; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        printf 'Missing build tool: %s\n' "$tool" >&2
        exit 1
    fi
done

if ! printf '#include <SDL2/SDL.h>\n' | cc -E -x c - >/dev/null 2>&1; then
    printf 'SDL2 development headers are missing or not in the compiler include path.\n' >&2
    exit 1
fi

if [ ! -x "$VENV/bin/python" ]; then
    "$PYTHON" -m venv "$VENV"
fi

"$VENV/bin/python" -c '
import platform
import sys
if sys.version_info[:2] != (3, 13) or platform.machine() != "x86_64":
    raise SystemExit(
        ".venv uses a different Python version or architecture; "
        "remove it manually and rerun this script"
    )
'

"$VENV/bin/python" -m pip install -r "$ROOT/requirements-linux.txt"

(
    cd "$ROOT/rectbinpack"
    "$VENV/bin/python" rbp_builder.py
)

(
    cd "$ROOT"
    "$VENV/bin/python" builder.py
)

printf 'Linux build completed:\n  %s\n  %s\n' \
    "$ROOT/build/remote.so" \
    "$ROOT/rectbinpack/_rbp extension"
