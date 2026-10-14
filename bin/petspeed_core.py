"""Reader for the PETSPEED 64 Speedcode executable format."""

from dataclasses import dataclass

from basic_v2 import BasicLine, tokenize


class Symbols:
    """Assign unique C64 BASIC names to address-based compiled variables."""

    def __init__(self):
        self.names = {}
        self.suffixes = {}
        self.next_index = 0

    def name(self, kind: str, address: int, suffix: str = "") -> str:
        key = kind, address
        if suffix not in ("", "$", "%"):
            raise ValueError("invalid BASIC variable type")
        if key not in self.names:
            while True:
                index = self.next_index
                self.next_index += 1
                prefix = chr(ord("A") + index // 36)
                tail = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"[index % 36]
                candidate = prefix + tail
                if prefix > "Z":
                    raise ValueError("too many BASIC variables")
                if candidate not in {"TI", "ST", "DS"} and tokenize(candidate) == candidate.encode("ascii"):
                    break
            self.names[key] = candidate + suffix
            self.suffixes[key] = suffix
        elif self.suffixes[key] != suffix:
            raise ValueError("conflicting BASIC variable types")
        return self.names[key]


@dataclass(frozen=True)
class DataItem:
    text: str
    tag: int
    numeric: bytes


@dataclass(frozen=True)
class Image:
    load: int
    sections: tuple[int, int, int, int, int]
    data: bytes

    def offset(self, address: int) -> int:
        offset = address - self.load + 2
        if offset < 2 or offset > len(self.data):
            raise ValueError(f"address ${address:04X} outside PETSPEED image")
        return offset

    @property
    def code_start(self) -> int:
        return self.sections[3] + 1

    @property
    def code(self) -> bytes:
        return self.data[self.offset(self.code_start):self.offset(self.sections[4])]

    def byte(self, address: int) -> int:
        offset = self.offset(address)
        if offset == len(self.data):
            raise ValueError(f"truncated Speedcode at ${address:04X}")
        return self.data[offset]

    def word(self, address: int) -> int:
        return self.byte(address) | self.byte(address + 1) << 8

    def payload(self, address: int, length: int) -> bytes:
        start = self.offset(address)
        end = self.offset(address + length)
        return self.data[start:end]

    def handler(self, opcode: int) -> int:
        """Resolve a high-bit Speedcode instruction via its image's dispatch table."""
        if not 0x80 <= opcode <= 0xff:
            raise ValueError("only high-bit opcodes have dispatch handlers")
        return self.word(0x0826 + 2 * (opcode - 0x80))

    def data_items(self) -> list[DataItem]:
        """Read the source DATA fields; the final region byte is a footer."""
        first, end = self.sections[:2]
        items = []
        address = first
        while address < end - 1:
            tag = self.byte(address)
            address += 1
            if 1 <= tag < 0x40:
                length, extra = tag, 0
            elif 0x40 <= tag < 0x80:
                length, extra = tag - 0x40, 1
            elif 0x80 <= tag < 0xc0:
                length, extra = tag - 0x80, 2
            else:
                raise ValueError(f"unsupported DATA tag ${tag:02X} at ${address - 1:04X}")
            if address + length + extra > end - 1:
                raise ValueError("truncated PETSPEED DATA item")
            text = self.payload(address, length).decode("latin-1")
            address += length
            numeric = self.payload(address, extra)
            address += extra
            items.append(DataItem(text, tag, numeric))
        return items


def data_lines(items: list[DataItem], start: int = 50000) -> list[BasicLine]:
    """Repackage sequential DATA fields into short, runnable BASIC lines."""
    lines = []
    fields = []
    for item in items:
        text = item.text
        if ('"' in text and not (text.startswith('"') and text.endswith('"'))):
            raise ValueError("DATA field contains unsupported quotation marks")
        if any(char in text for char in (",", ":")) and not text.startswith('"'):
            text = '"' + text + '"'
        if len("DATA " + text) > 230:
            raise ValueError("DATA field exceeds BASIC line limits")
        if fields and (len(fields) == 12 or len("DATA " + ",".join(fields + [text])) > 230):
            lines.append(BasicLine(start + len(lines), tokenize("DATA " + ",".join(fields))))
            fields = []
        fields.append(text)
    if fields:
        lines.append(BasicLine(start + len(lines), tokenize("DATA " + ",".join(fields))))
    if lines and lines[-1].number > 63999:
        raise ValueError("DATA requires too many BASIC lines")
    return lines


def read_image(data: bytes) -> Image:
    if len(data) < 0x27:
        raise ValueError("truncated PETSPEED program")
    load = int.from_bytes(data[:2], "little")
    if load != 0x0801 or data[0x1a:0x1d] != b"\x4c\x67\x22":
        raise ValueError("not a PETSPEED 64 executable")
    sections = tuple(int.from_bytes(data[i:i + 2], "little") for i in range(0x1d, 0x27, 2))
    if not (load < sections[0] < sections[1] <= sections[2] < sections[3] < sections[4]
            and sections[4] - load + 2 <= len(data)):
        raise ValueError("invalid PETSPEED section pointers")
    return Image(load, sections, data)


def decompile(data: bytes) -> list[BasicLine]:
    image = read_image(data)
    from speedcode import decode

    lines = decode(image)
    if not lines or lines[-1].number >= 50000:
        raise ValueError("decoded program has no usable BASIC line numbers")
    return lines + data_lines(image.data_items())
