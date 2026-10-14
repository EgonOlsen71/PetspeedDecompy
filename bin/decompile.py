"""PETSPEED to Commodore 64 BASIC decompiler CLI and graphical interface."""

import argparse
from pathlib import Path

from basic_v2 import detokenize, write_program
from petspeed_core import decompile, read_image


def listing(lines):
    def ascii_text(body):
        return "".join(char if 32 <= ord(char) <= 126 else f"{{0x{ord(char):02X}}}"
                       for char in detokenize(body))

    return "\n".join(f"{line.number} {ascii_text(line.body)}" for line in lines) + "\n"


def gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext

    root = tk.Tk()
    root.title("PETSPEED decompiler")
    root.geometry("880x620")
    source = tk.StringVar()
    bar = tk.Frame(root)
    bar.pack(fill="x", padx=10, pady=10)
    tk.Entry(bar, textvariable=source).pack(side="left", fill="x", expand=True)
    tk.Button(bar, text="Open...", command=lambda: source.set(filedialog.askopenfilename() or source.get())).pack(side="left")
    output = scrolledtext.ScrolledText(root, wrap="none", font=("Courier New", 10))
    output.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def run():
        try:
            path = Path(source.get())
            lines = decompile(path.read_bytes())
            text = listing(lines)
            destination = path.with_suffix(".decompiled.prg")
            destination.write_bytes(write_program(lines))
            path.with_suffix(".decompiled.bas").write_text(text, encoding="ascii")
            output.delete("1.0", "end")
            output.insert("1.0", text)
            root.title(f"PETSPEED decompiler - {destination.name}")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Decompilation failed", str(exc))

    tk.Button(root, text="Decompile and save .prg + .bas", command=run).pack(pady=(0, 10))
    root.mainloop()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, help="compiled PETSPEED PRG")
    parser.add_argument("-o", "--output", type=Path, help="output prefix (default: input.decompiled)")
    parser.add_argument("--gui", action="store_true", help="open graphical interface")
    parser.add_argument("--inspect", action="store_true", help="show compiled image layout without decompiling")
    args = parser.parse_args(argv)
    if args.gui:
        gui()
        return
    if args.input is None:
        parser.error("input PRG required unless --gui is used")
    try:
        if args.inspect:
            image = read_image(args.input.read_bytes())
            for name, address in zip(("DATA", "ARRAYS", "INITIALIZATION", "CODE METADATA", "END"), image.sections):
                print(f"{name:16} ${address:04X}")
            print(f"SPEEDCODE        ${image.code_start:04X} ({len(image.code)} bytes)")
            return
        lines = decompile(args.input.read_bytes())
        prefix = args.output or Path(str(args.input.with_suffix("")) + ".decompiled")
        binary = Path(str(prefix) + ".prg")
        ascii_file = Path(str(prefix) + ".bas")
        if binary.resolve() == args.input.resolve() or ascii_file.resolve() == args.input.resolve():
            raise ValueError("output path would overwrite compiled input")
        binary.write_bytes(write_program(lines))
        ascii_file.write_text(listing(lines), encoding="ascii")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"decompile: {exc}\n")
    print(f"Wrote {binary} and {ascii_file}")


if __name__ == "__main__":
    main()
