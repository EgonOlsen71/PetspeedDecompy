# PETSPEED 64 decompiler

Requires Python 3.10 or newer. The command-line decompiler uses only the Python standard library, so there is no `pip install` step. The graphical interface requires Tkinter (`python3-tk` on Linux; normally included with Python on Windows).

Decompile one PETSPEED-compiled C64 PRG:

```sh
python bin/decompile.py pcode/balls.wow.prg
```

This writes `pcode/balls.wow.decompiled.prg` (tokenized BASIC V2, load address `$0801`) and `pcode/balls.wow.decompiled.bas` (an ASCII listing). Use `-o path/to/prefix` to choose another output location, or `--inspect` to show compiled section addresses without exporting.

For the graphical file-picker interface, run `run-ui.cmd` on Windows or `sh run-ui.sh` on Unix. You can also run `python bin/decompile.py --gui` directly.

To decompile every `.prg` in `pcode`, run `test/decompile_all.cmd` in Command Prompt or `sh test/decompile_all.sh` on Unix. Both scripts write the resulting PRGs and listings into `test/output`. The shell script uses `python3` when available, or `python`; set `PYTHON` to override it.

Some binaries contain PETSPEED's own *undefined statement* markers. Their lost statement targets are not stored in the compiled images and cannot be faithfully reconstructed from the binary alone. The batch scripts continue past errors and exit unsuccessfully if any input fails.

Run regression tests with `python -m unittest discover -s bin -v`. Unsupported Speedcode operations stop with an error rather than producing an incomplete BASIC program. Original source variable names and line numbers cannot be recovered from the compiled images; the decompiler assigns new ones.
