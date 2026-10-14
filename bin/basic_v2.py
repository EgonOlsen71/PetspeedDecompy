"""Commodore 64 BASIC V2 program and token encoding."""

from dataclasses import dataclass


KEYWORDS = (
    "END", "FOR", "NEXT", "DATA", "INPUT#", "INPUT", "DIM", "READ",
    "LET", "GOTO", "RUN", "IF", "RESTORE", "GOSUB", "RETURN", "REM",
    "STOP", "ON", "WAIT", "LOAD", "SAVE", "VERIFY", "DEF", "POKE",
    "PRINT#", "PRINT", "CONT", "LIST", "CLR", "CMD", "SYS", "OPEN",
    "CLOSE", "GET", "NEW", "TAB(", "TO", "FN", "SPC(", "THEN", "NOT",
    "STEP", "+", "-", "*", "/", "^", "AND", "OR", ">", "=", "<",
    "SGN", "INT", "ABS", "USR", "FRE", "POS", "SQR", "RND", "LOG",
    "EXP", "COS", "SIN", "TAN", "ATN", "PEEK", "LEN", "STR$", "VAL",
    "ASC", "CHR$", "LEFT$", "RIGHT$", "MID$", "GO",
)
TOKEN_TO_WORD = {i + 0x80: word for i, word in enumerate(KEYWORDS)}
WORD_TO_TOKEN = {word: token for token, word in TOKEN_TO_WORD.items()}
WORD_ORDER = sorted(WORD_TO_TOKEN, key=len, reverse=True)


@dataclass(frozen=True)
class BasicLine:
    number: int
    body: bytes


def read_program(data: bytes) -> list[BasicLine]:
    """Read a linked, load-address-prefixed C64 BASIC PRG."""
    if len(data) < 4:
        raise ValueError("truncated BASIC PRG")
    base = int.from_bytes(data[:2], "little")
    address = base
    lines = []
    visited = set()
    while True:
        offset = address - base + 2
        if offset < 2 or offset + 2 > len(data) or address in visited:
            raise ValueError("invalid BASIC line pointer")
        visited.add(address)
        next_address = int.from_bytes(data[offset:offset + 2], "little")
        if next_address == 0:
            return lines
        if next_address <= address or offset + 4 > len(data):
            raise ValueError("invalid BASIC line pointer")
        end = data.find(b"\0", offset + 4)
        if end < 0 or end + 1 != next_address - base + 2:
            raise ValueError("invalid BASIC line length")
        lines.append(BasicLine(int.from_bytes(data[offset + 2:offset + 4], "little"), data[offset + 4:end]))
        address = next_address


def write_program(lines: list[BasicLine], base: int = 0x0801) -> bytes:
    result = bytearray(base.to_bytes(2, "little"))
    address = base
    for line in lines:
        if not 0 <= line.number <= 63999 or b"\0" in line.body or len(line.body) > 250:
            raise ValueError("invalid BASIC line")
        next_address = address + len(line.body) + 5
        if next_address > 0xffff:
            raise ValueError("BASIC program exceeds address space")
        result.extend(next_address.to_bytes(2, "little"))
        result.extend(line.number.to_bytes(2, "little"))
        result.extend(line.body)
        result.append(0)
        address = next_address
    result.extend(b"\0\0")
    return bytes(result)


def tokenize(text: str) -> bytes:
    """Tokenize BASIC text, keeping literal characters in quotes, DATA and REM."""
    result = bytearray()
    quoted = False
    literal = False
    data = False
    index = 0
    while index < len(text):
        char = text[index]
        if not quoted and not literal and not data:
            keyword = next((word for word in WORD_ORDER if text[index:index + len(word)].upper() == word), None)
            if keyword:
                result.append(WORD_TO_TOKEN[keyword])
                index += len(keyword)
                literal = keyword == "REM"
                data = keyword == "DATA"
                continue
        value = ord(char)
        if value > 255 or value == 0:
            raise ValueError("BASIC text contains a character outside PETSCII")
        result.append(value)
        if char == '"':
            quoted = not quoted
        elif char == ":" and not quoted and data:
            data = False
        index += 1
    return bytes(result)


def detokenize(body: bytes) -> str:
    result = []
    quoted = False
    literal = False
    data = False
    for value in body:
        if value in TOKEN_TO_WORD and not quoted and not literal and not data:
            word = TOKEN_TO_WORD[value]
            result.append(word)
            literal = word == "REM"
            data = word == "DATA"
        else:
            result.append(chr(value))
            if value == ord('"'):
                quoted = not quoted
            elif value == ord(":") and not quoted and data:
                data = False
    return "".join(result)
