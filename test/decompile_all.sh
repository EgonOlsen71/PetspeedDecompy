#!/bin/sh
set -u

SCRIPT_DIR=$(CDPATH= cd -P "$(dirname "$0")" && pwd) || exit 1
ROOT=$(dirname "$SCRIPT_DIR")
OUTPUT="$SCRIPT_DIR/output"
mkdir -p "$OUTPUT" || exit 1

if [ -n "${PYTHON:-}" ]; then
    interpreter=$PYTHON
elif command -v python3 >/dev/null 2>&1; then
    interpreter=python3
else
    interpreter=python
fi
root_arg=$ROOT
output_arg=$OUTPUT
windows_python=0
if command -v cygpath >/dev/null 2>&1; then
    case "$("$interpreter" -c 'import sys; print(sys.platform)' 2>/dev/null)" in
        win32*)
            windows_python=1
            root_arg=$(cygpath -w "$ROOT")
            output_arg=$(cygpath -w "$OUTPUT")
            ;;
    esac
fi

found=0
failed=0
for input in "$ROOT"/pcode/*.prg; do
    [ -f "$input" ] || continue
    found=1
    name=${input##*/}
    name=${name%.prg}
    input_arg=$input
    if [ "$windows_python" -eq 1 ]; then
        input_arg=$(cygpath -w "$input")
    fi
    printf 'Decompiling %s\n' "${input##*/}"
    "$interpreter" "$root_arg/bin/decompile.py" "$input_arg" -o "$output_arg/$name.decompiled" || failed=1
done
if [ "$found" -eq 0 ]; then
    printf 'No compiled PRG files found in %s\n' "$ROOT/pcode" >&2
    exit 1
fi
exit "$failed"
