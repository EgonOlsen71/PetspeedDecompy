"""Regression checks for PETSPEED compiled files."""

from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
import csv
from io import StringIO
from tempfile import TemporaryDirectory
import re
import unittest
from unittest.mock import patch

from basic_v2 import BasicLine, detokenize, read_program, tokenize, write_program
from decompile import listing, main
from petspeed_core import DataItem, Symbols, data_lines, decompile, read_image
from speedcode import decode, float_literal, instructions


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "pcode"


def data_clause(body):
    quoted = False
    for index, char in enumerate(body):
        if char == '"':
            quoted = not quoted
        elif char == ":" and not quoted:
            return body[:index]
    return body


class ImageTests(unittest.TestCase):
    def test_compiled_examples(self):
        for path in FIXTURES.glob("*.wow.prg"):
            with self.subTest(path=path.name):
                image = read_image(path.read_bytes())
                self.assertEqual(image.code[-2:], b"\xd3\xd3")
                self.assertGreater(len(image.code), 100)
                self.assertEqual(image.handler(0xd1), 0x12ed)
                self.assertEqual(image.handler(0xd2), 0x12fc)

    def test_reject_uncompiled_basic(self):
        with self.assertRaises(ValueError):
            read_image((ROOT / "basic" / "divide.prg").read_bytes())

    def test_trailing_bytes_are_not_executable(self):
        source = (FIXTURES / "divide.wow.prg").read_bytes()
        self.assertEqual(read_image(source + b"\x00").code, read_image(source).code)
        interpreter = read_image((ROOT / "petspeed" / "pass3.prg").read_bytes())
        self.assertEqual(interpreter.code_start, 0x373d)

    def test_data_items_and_output_lines(self):
        expected = {"compsuite.wow.prg": 204, "demo.wow.prg": 87,
                    "laby.wow.prg": 385, "lyrix.wow.prg": 1029}
        for path in FIXTURES.glob("*.wow.prg"):
            with self.subTest(path=path.name):
                items = read_image(path.read_bytes()).data_items()
                self.assertEqual(len(items), expected.get(path.name, 0))
                lines = data_lines(items)
                self.assertEqual(read_program(write_program(lines)), lines)
                output_fields = [field for line in lines
                                 for field in next(csv.reader([detokenize(line.body)[5:]]))]
                self.assertEqual(output_fields, [item.text for item in items])
        items = read_image((FIXTURES / "compsuite.wow.prg").read_bytes()).data_items()
        self.assertEqual([item.text for item in items[:3]], ["120", "173", "20"])
        for name in ("compsuite", "demo", "laby", "lyrix"):
            with self.subTest(source=name):
                if not (FIXTURES / f"{name}.wow.prg").exists():
                    continue
                source = read_program((ROOT / "basic" / f"{name}.prg").read_bytes())
                fields = [field.strip() for line in source if line.body.startswith(bytes([0x83]))
                          for field in next(csv.reader([data_clause(detokenize(line.body)[5:])]))]
                decoded = read_image((FIXTURES / f"{name}.wow.prg").read_bytes()).data_items()
                self.assertEqual([item.text for item in decoded], fields)

    def test_generated_names_are_unique_basic_identifiers(self):
        symbols = Symbols()
        names = [symbols.name("scalar", index) for index in range(927)]
        self.assertEqual(len(set(names)), 927)
        self.assertTrue({"TI", "ST", "DS"}.isdisjoint(names))
        self.assertTrue(all(tokenize(name) == name.encode("ascii") for name in names))
        self.assertEqual(symbols.name("scalar", 0), names[0])
        with self.assertRaises(ValueError):
            symbols.name("scalar", 0, "%")
        with self.assertRaises(ValueError):
            symbols.name("array", 9999)

    def test_data_delimiters_are_quoted(self):
        items = [DataItem("A,B", 3, b""), DataItem("C:D", 3, b"")]
        self.assertEqual(detokenize(data_lines(items)[0].body), 'DATA "A,B","C:D"')

    def test_float_exponents_use_basic_spelling(self):
        self.assertIn("E+", float_literal(bytes([0xb0, 0, 0, 0, 0, 0])))

    def test_numeric_input_rejects_string_scalar(self):
        data = bytearray((FIXTURES / "balls.wow.prg").read_bytes())
        image = read_image(data)
        data[image.offset(0x2808 + 6)] = 0xff
        with self.assertRaises(ValueError):
            decode(read_image(data))

    def test_unseen_combination_of_opcode_families(self):
        data = bytearray((FIXTURES / "divide.wow.prg").read_bytes())
        image = read_image(data)
        string_conversion = next(ins for ins in instructions(image) if ins.opcode == 0xc4)
        data[image.offset(string_conversion.address)] = 0xc7  # STR$ -> CHR$, same operand width.
        lines = decompile(bytes(data))
        self.assertIn("CHR$", listing(lines))
        self.assertEqual(read_program(write_program(lines)), lines)

    def test_array_layout_is_inferred_not_fixture_coded(self):
        from speedcode import array_layout

        image = read_image((FIXTURES / "compsuite.wow.prg").read_bytes())
        layout, aliases, bases = array_layout(image, instructions(image))
        self.assertEqual(sorted(shape for _, shape in layout.values()), [(6, 6), (11,), (21,), (21,)])
        self.assertEqual(len(aliases), 1)
        self.assertEqual(len(bases), 4)
        snake = read_image((FIXTURES / "snake.wow.prg").read_bytes())
        snake_layout, _, _ = array_layout(snake, instructions(snake))
        self.assertIn((2, (2, 1000)), snake_layout.values())

    def test_nested_array_reads_preserve_assignment_destination(self):
        lines = {line.number: detokenize(line.body)
                 for line in decompile((FIXTURES / "compsuite.wow.prg").read_bytes())}
        for number in (2780, 2800, 2830, 2860, 2890):
            self.assertTrue(lines[number].startswith("A1(A7%)=A2("))

    def test_bare_next_and_print_before_run(self):
        suite = {line.number: detokenize(line.body)
                 for line in decompile((FIXTURES / "compsuite.wow.prg").read_bytes())}
        self.assertEqual([suite[number] for number in (2430, 2440, 2450, 2460, 2470)], ["NEXT"] * 5)
        laby = {line.number: detokenize(line.body)
                for line in decompile((FIXTURES / "laby.wow.prg").read_bytes())}
        self.assertTrue(laby[1250].startswith("PRINT "))
        self.assertEqual(laby[1260], "RUN")

    def test_invalid_two_dimensional_stride_is_rejected(self):
        data = bytearray((FIXTURES / "compsuite.wow.prg").read_bytes())
        image = read_image(data)
        data[image.offset(image.sections[2])] = 7
        with self.assertRaises(ValueError):
            decompile(bytes(data))

    def test_read_selector_is_not_dispatched_as_literal(self):
        data = bytearray((ROOT / "petspeed" / "pass3.prg").read_bytes())
        image = read_image(data)
        data[0x25:0x27] = (0x385c).to_bytes(2, "little")
        data[image.offset(0x385a):image.offset(0x385c)] = b"\xd3\xd3"
        parsed = instructions(read_image(data))
        self.assertEqual([(ins.opcode, bytes(ins.argument)) for ins in parsed[-3:-1]],
                         [(0xd9, b"\x42"), (0xd5, b"")])

    def test_undefined_statement_is_reported_without_inventing_branch(self):
        for name, line in (("colors", 20), ("lyrix", 181)):
            path = FIXTURES / f"{name}.wow.prg"
            if path.exists():
                with self.subTest(program=name):
                    with self.assertRaisesRegex(ValueError, rf"undefined statement at source line {line}"):
                        decompile(path.read_bytes())

    def test_listing_escapes_petscii(self):
        text = listing([BasicLine(10, tokenize('PRINT "\x93HELLO"'))])
        self.assertEqual(text, '10 PRINT "{0x93}HELLO"\n')
        text.encode("ascii")

    def test_ascii_listings_for_all_originals(self):
        for path in (ROOT / "basic").glob("*.prg"):
            with self.subTest(path=path.name):
                listing(read_program(path.read_bytes())).encode("ascii")

    def test_decode_divide_fixture(self):
        lines = decompile((FIXTURES / "divide.wow.prg").read_bytes())
        text = listing(lines)
        self.assertIn('"TEILE..."', text)
        self.assertIn("GOSUB", text)
        self.assertEqual(read_program(write_program(lines)), lines)

    def test_decode_demo_fixture(self):
        lines = decompile((FIXTURES / "demo.wow.prg").read_bytes())
        text = listing(lines)
        self.assertIn("bASIC-bOSS", text)
        self.assertIn("GOSUB", text)
        self.assertIn('TI$<"000040"', text)
        self.assertIn("PRINT (TI/60)", text)
        self.assertEqual(read_program(write_program(lines)), lines)

    def test_compiled_data_is_attached_once(self):
        for name in ("compsuite", "laby"):
            with self.subTest(program=name):
                image = read_image((FIXTURES / f"{name}.wow.prg").read_bytes())
                lines = decompile(image.data)
                fields = [field for line in lines if line.number >= 50000
                          for field in next(csv.reader([detokenize(line.body)[5:]]))]
                self.assertEqual(fields, [item.text for item in image.data_items()])

    def test_laby_extended_slots_do_not_alias_compact_variables(self):
        image = read_image((FIXTURES / "laby.wow.prg").read_bytes())
        parsed = instructions(image)
        joystick = next(ins for ins in parsed if ins.address == 0x2fd4)
        counter = next(ins for ins in parsed if ins.address == 0x33dd)
        self.assertEqual((joystick.scalar_address, counter.scalar_address), (0x2938, 0x2838))
        lines = {line.number: detokenize(line.body) for line in decompile(image.data)}
        mask = lines[130].split("=")[0]
        count = lines[1790].split("=")[0]
        self.assertNotEqual(mask, count)
        self.assertIn(mask, lines[930])
        self.assertIn("=0 THEN", lines[2920])
        self.assertIn("=0 THEN", lines[3020])

    def test_supported_fixture_branches_and_output(self):
        expected = {"balls": ("NUMBER OF BALL", "POKE 53280", "RND("),
                    "demo": ("bASIC-bOSS", "ON ", "FRE(0)"),
                    "lines": ("POKE 56576", "GOSUB", "RND("),
                    "divide": ("TEILE...", "GOSUB", "GET "),
                    "fiddly": ("BIT FIDDLER", "GET ", "POKE 646"),
                    "scan": ("DISK SCANNER", "OPEN 2,8,2", "SYS 65478"),
                    "compsuite": ("TESTS FAILED", "ON ", "WAIT 198,1"),
                    "laby": ("POKE 56576", "RUN", "READ "),
                    "snake": ("AUA!", "GOSUB", "DIM ")}
        for name in ("balls", "demo", "lines", "divide", "fiddly", "scan", "compsuite", "laby", "snake"):
            with self.subTest(program=name):
                lines = decompile((FIXTURES / f"{name}.wow.prg").read_bytes())
                self.assertEqual(read_program(write_program(lines)), lines)
                self.assertEqual([line.number for line in lines], sorted(line.number for line in lines))
                text = listing(lines)
                for landmark in expected[name]:
                    self.assertIn(landmark, text)
                numbers = {line.number for line in lines}
                for target in re.findall(r"\b(?:GOTO|GOSUB|THEN)\s+(\d+)", text):
                    self.assertIn(int(target), numbers)
                for table in re.findall(r"\bON\s+[^\n]*?\b(?:GOTO|GOSUB)\s+([\d,]+)", text):
                    for target in table.split(","):
                        self.assertIn(int(target), numbers)

    def test_cli_does_not_replace_compiled_input(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "example.wow.prg"
            source.write_bytes(b"compiled input")
            with patch("decompile.decompile", return_value=[BasicLine(10, tokenize("END"))]):
                with redirect_stdout(StringIO()):
                    main([str(source)])
            self.assertEqual(source.read_bytes(), b"compiled input")
            self.assertTrue((Path(directory) / "example.wow.decompiled.prg").exists())
            self.assertTrue((Path(directory) / "example.wow.decompiled.bas").exists())

    def test_cli_does_not_emit_unverified_program(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "invalid.prg"
            source.write_bytes(b"not a compiled program")
            with redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit):
                    main([str(source)])
            self.assertEqual(list(Path(directory).glob("*.decompiled.*")), [])

    def test_unknown_compiled_opcode_does_not_emit_program(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "modified.wow.prg"
            data = bytearray((FIXTURES / "divide.wow.prg").read_bytes())
            image = read_image(data)
            data[image.offset(image.code_start)] = 0xfa
            source.write_bytes(data)
            with redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit):
                    main([str(source)])
            self.assertEqual(list(Path(directory).glob("*.decompiled.*")), [])

    def test_cli_exports_real_compiled_fixture(self):
        with TemporaryDirectory() as directory:
            for name in ("balls", "demo", "lines", "divide", "fiddly", "scan", "compsuite", "laby", "snake"):
                with self.subTest(program=name):
                    source = Path(directory) / f"{name}.wow.prg"
                    original = (FIXTURES / source.name).read_bytes()
                    source.write_bytes(original)
                    with redirect_stdout(StringIO()):
                        main([str(source)])
                    binary = Path(directory) / f"{name}.wow.decompiled.prg"
                    ascii_file = Path(directory) / f"{name}.wow.decompiled.bas"
                    lines = read_program(binary.read_bytes())
                    self.assertEqual(listing(lines), ascii_file.read_text(encoding="ascii"))
                    self.assertGreater(len(lines), 50)
                    self.assertEqual(source.read_bytes(), original)

    def test_cli_rejects_explicit_input_collision(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / "balls.wow.prg"
            original = (FIXTURES / source.name).read_bytes()
            source.write_bytes(original)
            with redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit):
                    main([str(source), "-o", str(source.with_suffix(""))])
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
