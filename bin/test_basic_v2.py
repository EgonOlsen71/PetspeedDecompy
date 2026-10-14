"""Tests for the BASIC V2 file and token codec."""

from pathlib import Path
import unittest

from basic_v2 import BasicLine, detokenize, read_program, tokenize, write_program


class BasicV2Tests(unittest.TestCase):
    def test_original_programs_round_trip(self):
        for path in (Path(__file__).resolve().parent.parent / "basic").glob("*.prg"):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                lines = read_program(original)
                self.assertEqual(write_program(lines), original)
                for line in lines:
                    self.assertEqual(tokenize(detokenize(line.body)), line.body)

    def test_generated_program(self):
        lines = [BasicLine(10, tokenize('PRINT "HELLO"')), BasicLine(20, tokenize("GOTO 10"))]
        self.assertEqual(read_program(write_program(lines)), lines)

    def test_literals(self):
        for text in ('DATA PRINT,"GOTO":PRINT 1', 'REM PRINT:GOTO 10', 'PRINT "GOTO":IF A=1 THEN 10'):
            with self.subTest(text=text):
                self.assertEqual(detokenize(tokenize(text)), text)

    def test_preserve_string_case(self):
        self.assertEqual(detokenize(tokenize('PRINT "Hello"')), 'PRINT "Hello"')

    def test_corrupt_pointer(self):
        with self.assertRaises(ValueError):
            read_program(b"\x01\x08\x01\x08\x0a\x00\x00")

    def test_reject_oversized_basic_line(self):
        with self.assertRaises(ValueError):
            write_program([BasicLine(10, b"X" * 251)])


if __name__ == "__main__":
    unittest.main()
