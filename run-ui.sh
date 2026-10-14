#!/bin/sh
set -u

SCRIPT_DIR=$(CDPATH= cd -P "$(dirname "$0")" && pwd) || exit 1
if [ -n "${PYTHON:-}" ]; then
    interpreter=$PYTHON
elif command -v python3 >/dev/null 2>&1; then
    interpreter=python3
else
    interpreter=python
fi
script="$SCRIPT_DIR/bin/decompile.py"
if command -v cygpath >/dev/null 2>&1; then
    case "$("$interpreter" -c 'import sys; print(sys.platform)' 2>/dev/null)" in
        win32*) script=$(cygpath -w "$script") ;;
    esac
fi
exec "$interpreter" "$script" --gui
