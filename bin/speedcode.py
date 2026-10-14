"""PETSPEED 64 Speedcode instruction decoder and BASIC reconstruction.

Instruction semantics follow the handler table embedded in each executable;
variable names and BASIC line numbers are generated because neither survives
compilation.
"""

from dataclasses import dataclass

from basic_v2 import BasicLine, tokenize
from petspeed_core import Image, Symbols


_LITERALS = {0x40: 2, 0x43: 6, 0x46: -1, 0x49: 2,
             0x4c: 6, 0x4f: -1, 0x52: 1, 0x55: 1}
_OPERANDS = {0x80: 1, 0xa7: 2, 0xac: 2, 0xcd: 2, 0xd1: 2, 0xd2: 2,
             0xd4: 1, 0xe1: 2, 0xed: 2, 0xee: 2, 0xef: 2,
             0xf0: 2, 0xf1: 2, 0xf2: 2, 0xf3: 2, 0xf4: 2,
             0xfb: 2, 0xfc: 2, 0xfd: 1, 0xfe: 1, 0xff: 1}
_HANDLERS = {
    0x80: 0x19a4, 0x81: 0x1ad4, 0x82: 0x1a9b, 0x83: 0x1b50,
    0x84: 0x1bfe, 0x85: 0x1c2a, 0x87: 0x1a79, 0x88: 0x1b11,
    0x89: 0x1bf5, 0x8a: 0x1414, 0x8b: 0x1214, 0x8c: 0x121d,
    0x8d: 0x11a5, 0x8f: 0x11bd, 0x90: 0x11ea, 0x91: 0x1dd0,
    0x92: 0x1e39, 0x93: 0x120b, 0x94: 0x1202, 0x95: 0x1226,
    0x96: 0x122f, 0x97: 0x1420, 0x98: 0x1d4a, 0x99: 0x1d4e,
    0x9b: 0x1d56, 0x9c: 0x1d41, 0x9d: 0x1d38,
    0x9e: 0x13fc, 0x9f: 0x1f84,
    0xa0: 0x1f84, 0xa1: 0x21df, 0xa2: 0x1fe2, 0xa3: 0x1fe2,
    0xa4: 0x23e5, 0xa5: 0x201d, 0xa6: 0x201d,
    0xa7: 0x2394, 0xa8: 0x21df, 0xa9: 0x1f24,
    0xaa: 0x1ee4, 0xab: 0x1408,
    0xac: 0x1098, 0xad: 0x18ba, 0xae: 0x18be, 0xaf: 0x18c2,
    0xb0: 0x18d0, 0xb1: 0x1900, 0xb2: 0x1900, 0xb3: 0x142c,
    0xb4: 0x170a, 0xb5: 0x16f3, 0xb6: 0x1725, 0xb8: 0x1f6d,
    0xb9: 0x16e9, 0xba: 0x175b, 0xbb: 0x1747, 0xbc: 0x177f,
    0xc2: 0x1811, 0xc3: 0x1ccf, 0xc4: 0x1e93, 0xc5: 0x1cdd,
    0xc6: 0x1f58, 0xc7: 0x1ec0, 0xc8: 0x2364, 0xca: 0x2267,
    0xcb: 0x0d5a, 0xcc: 0x0c9b, 0xcd: 0x0d97, 0xce: 0x17c0,
    0xcf: 0x0bbc, 0xd0: 0x0c6d, 0xd1: 0x12ed, 0xd2: 0x12fc,
    0xd3: 0x236a, 0xd4: 0x12ca, 0xd5: 0x0ee7, 0xd6: 0x146d,
    0xd7: 0x15cc, 0xd8: 0x1315, 0xd9: 0x163c, 0xda: 0x16a1,
    0xdc: 0x1855,
    0xdd: 0x1e4e, 0xde: 0x1e6d, 0xe0: 0x1eeb, 0xe1: 0x18a8,
    0xe2: 0x133f, 0xe3: 0x18a1, 0xe5: 0x190d, 0xe7: 0x0c46,
    0xe6: 0x191a, 0xe8: 0x179a, 0xe9: 0x1927, 0xeb: 0x16ce, 0xec: 0x0c40,
    0xed: 0x2089, 0xee: 0x2076, 0xef: 0x20b4, 0xf0: 0x206a,
    0xf1: 0x2064, 0xf2: 0x2070, 0xf3: 0x20f8,
    0xf4: 0x20ca, 0xf5: 0x1395,
    0xf6: 0x13c0, 0xf7: 0x13de, 0xf8: 0x210e, 0xf9: 0x20e0,
    0xfa: 0x2370, 0xfb: 0x240f, 0xfc: 0x21af, 0xfd: 0x246a,
    0xfe: 0x246a, 0xff: 0x246a,
}


@dataclass(frozen=True)
class Instruction:
    address: int
    opcode: int
    argument: bytes | tuple[int, ...]
    after: int

    @property
    def scalar_address(self) -> int | None:
        if self.opcode < 0x40 or 0x60 <= self.opcode < 0x80:
            return 0x2800 + 8 * (self.opcode & 31)
        if self.opcode in (0xfd, 0xfe, 0xff):
            return 0x2900 + 7 * self.argument[0]
        return None


def instructions(image: Image) -> list[Instruction]:
    """Parse a complete Speedcode stream, bounded by the image header."""
    pc, end = image.code_start, image.sections[4]
    result = []
    while pc < end:
        address = pc
        op = image.byte(pc)
        pc += 1
        if op == 0x58:
            if pc + 2 > end:
                raise ValueError(f"truncated undefined-statement marker at ${address:04X}")
            line = image.word(pc)
            raise ValueError(f"PETSPEED undefined statement at source line {line} "
                             f"(Speedcode ${address:04X}); missing statement cannot be recovered")
        if 0x40 <= op < 0x60:
            if op not in _LITERALS:
                raise ValueError(f"unknown literal ${op:02X} at ${address:04X}")
            size = _LITERALS[op]
            if size == -1:
                if pc >= end:
                    raise ValueError(f"truncated string at ${address:04X}")
                size = image.byte(pc) + 1
        else:
            if op >= 0x80 and image.handler(op) != _HANDLERS.get(op):
                raise ValueError(f"unknown handler ${op:02X} at ${address:04X}")
            size = _OPERANDS.get(op, 0)
        if op in (0xd7, 0xd9, 0xda) and pc < end and image.byte(pc) in (0x41, 0x42):
            size = 1  # INPUT/READ can consume an inline array-store selector.
        if op == 0xfa:
            raise ValueError(f"unresolved variable-length opcode $FA at ${address:04X}")
        if pc + size > end:
            raise ValueError(f"truncated instruction at ${address:04X}")
        arg = image.payload(pc, size)
        pc += size
        if op == 0xe2:
            if pc >= end:
                raise ValueError(f"truncated ON table at ${address:04X}")
            length = image.byte(pc)
            if length < 4 or length % 2 or pc + length > end:
                raise ValueError(f"invalid ON table at ${address:04X}")
            table = image.payload(pc + 1, length - 1)
            if table[0] != 0xd1:
                raise ValueError(f"invalid ON GOTO at ${address:04X}")
            arg = tuple(int.from_bytes(table[i:i + 2], "little")
                        for i in range(1, len(table), 2))
            pc += length
        result.append(Instruction(address, op, arg, pc))
    if len(result) < 2 or (result[-2].opcode, result[-1].opcode) != (0xd3, 0xd3):
        raise ValueError("missing Speedcode end marker")
    return result[:-1]


def float_literal(data: bytes) -> str:
    exponent = data[0]
    if not exponent:
        return "0"
    mantissa = (1 << 31) | (int.from_bytes(data[1:5], "big") & 0x7fffffff)
    value = (-1 if data[5] & 0x80 else 1) * mantissa * 2.0 ** (exponent - 160)
    return format(value, ".10g").upper()


def string_literal(data: bytes) -> str:
    return '+CHR$(34)+'.join('"' + part + '"'
                              for part in data.decode("latin-1").split('"'))


def array_layout(image: Image, code: list[Instruction]):
    """Infer array element widths and shapes from references and relocations."""
    refs = sorted({int.from_bytes(ins.argument, "little") for ins in code if ins.opcode == 0xfc})
    direct = [int.from_bytes(ins.argument, "little") for ins in code
              if ins.opcode in (0xed, 0xf0, 0xf3, 0xf4)]
    if direct and (not refs or min(direct) < refs[0]):
        refs.insert(0, min(direct))
    if not refs:
        return {}, {}, []
    first, end = image.sections[1], image.sections[2] - 1
    if refs[-1] >= end:
        raise ValueError("unresolved array base")
    kinds, two_d = {}, {}
    selected = None
    for ins in code:
        op = ins.opcode
        if op == 0xfc:
            selected = int.from_bytes(ins.argument, "little")
        elif op in (0x9f, 0xa0, 0xa2, 0xa3) and selected is not None:
            width = 5 if op in (0x9f, 0xa0) else 2
            if selected in kinds and kinds[selected] != width:
                raise ValueError(f"conflicting array type at ${selected:04X}")
            kinds[selected] = width
        elif op in (0xa1, 0xa8) and selected is not None:
            two_d[selected] = None
    for ins in code:
        if ins.opcode in (0xf4, 0xf3):
            address = int.from_bytes(ins.argument, "little")
            base = max((base for base in refs if base <= address), default=None)
            if base is None:
                raise ValueError(f"direct store outside array at ${address:04X}")
            kinds.setdefault(base, 2 if ins.opcode == 0xf4 else 5)
    for base in two_d:
        for address in range(image.sections[2], image.sections[3] - 4, 5):
            record = image.payload(address, 5)
            if int.from_bytes(record[3:5], "little") == base - 3:
                stride = int.from_bytes(record[:2], "little")
                if stride < 2:
                    raise ValueError("invalid two-dimensional array stride")
                width = {0: 5, 1: 2}.get(record[2])
                if width is None or base in kinds and kinds[base] != width:
                    raise ValueError(f"unsupported two-dimensional element type at ${base:04X}")
                kinds[base] = width
                two_d[base] = stride
                break
        if two_d[base] is None:
            raise ValueError(f"missing array dimension record at ${base:04X}")
    if refs[0] != first and not (refs[0] in two_d and refs[0] - 3 == first):
        raise ValueError("unresolved array base")
    aliases = {}
    for base, stride in two_d.items():
        width = kinds[base]
        later = [candidate for candidate in refs if candidate > base]
        for candidate in later:
            offset = candidate - base
            if offset % (stride * width):
                break
            aliases[candidate] = base, offset // (stride * width)
        remaining = [candidate for candidate in refs if candidate > base and candidate not in aliases]
        stop = remaining[0] if remaining else end
        while (stop - base) % (stride * width) and any(root == base for root, _ in aliases.values()):
            candidate = max(candidate for candidate, (root, _) in aliases.items() if root == base)
            del aliases[candidate]
            stop = candidate
    bases = [base for base in refs if base not in aliases]
    layouts = {}
    for index, base in enumerate(bases):
        stop = bases[index + 1] if index + 1 < len(bases) else end
        if stop in two_d:
            stop -= 3  # Descriptor immediately precedes a 2D array's data.
        width = kinds.get(base)
        if width is None or stop <= base or (stop - base) % width:
            raise ValueError(f"unknown array layout at ${base:04X}")
        count = (stop - base) // width
        if base in two_d:
            stride = two_d[base]
            if count % stride:
                raise ValueError(f"invalid array dimensions at ${base:04X}")
            layouts[base] = width, (stride, count // stride)
        else:
            layouts[base] = width, (count,)
    for address in direct:
        base = max((base for base in bases if base <= address), default=None)
        if base is None or address - base >= layouts[base][0] * _element_count(layouts[base][1]):
            raise ValueError(f"direct element outside array at ${address:04X}")
    return layouts, aliases, bases


def _element_count(dimensions: tuple[int, ...]) -> int:
    result = 1
    for size in dimensions:
        result *= size
    return result


def decode(image: Image) -> list[BasicLine]:
    """Translate supported interpreter operations without program-name dispatch."""
    code = instructions(image)
    symbols = Symbols()
    scalar_end, array_start, array_end = image.sections[:3]
    if not 0x2800 < scalar_end <= array_start:
        raise ValueError("invalid variable records")
    layouts, aliases, bases = array_layout(image, code)
    arrays = {base: symbols.name("array", base, "%" if width == 2 else "")
              for base, (width, _) in layouts.items()}
    dimensions = [f"DIM {arrays[base]}({','.join(str(size - 1) for size in layouts[base][1])})"
                  for base in bases]
    string_addresses = set()
    for index, ins in enumerate(code[:-1]):
        following = code[index + 1]
        if ins.opcode in (0x46, 0xdc, 0xd7) and (0x60 <= following.opcode < 0x80 or following.opcode == 0xff):
            string_addresses.add(0x2800 + 8 * (following.opcode & 31)
                                 if following.opcode != 0xff else 0x2900 + 7 * following.argument[0])

    def scalar(address):
        if not 0x2800 <= address or address + 6 >= scalar_end:
            raise ValueError(f"invalid scalar address ${address:04X}")
        tag = image.byte(address + 6)
        if tag not in (0x05, 0x96, 0xff):
            raise ValueError(f"unknown variable descriptor ${tag:02X} at ${address:04X}")
        suffix = "$" if address in string_addresses or tag == 0xff else "%" if tag == 0x05 else ""
        return symbols.name("scalar", address, suffix)

    def variable(ins):
        op = ins.opcode
        if op in (0xfd, 0xfe, 0xff):
            return scalar(0x2900 + 7 * ins.argument[0])
        return scalar(0x2800 + 8 * (op & 31))

    def indexed(base, index):
        root, offset = aliases.get(base, (base, 0))
        if root not in layouts:
            raise ValueError(f"unknown array base ${base:04X}")
        width, shape = layouts[root]
        if len(shape) == 1:
            return f"{arrays[root]}({index})"
        columns = shape[0]
        linear = f"({offset * columns}+{index})" if offset else index
        row = f"INT(({linear})/{columns})"
        return f"{arrays[root]}(({linear})-({row}*{columns}),{row})"

    def direct(address, width):
        root = max((base for base in bases if base <= address), default=None)
        if root is None or layouts[root][0] != width or (address - root) % width:
            raise ValueError(f"invalid direct array reference ${address:04X}")
        index = (address - root) // width
        if index >= _element_count(layouts[root][1]):
            raise ValueError(f"array element outside allocation ${address:04X}")
        if len(layouts[root][1]) == 1:
            return f"{arrays[root]}({index})"
        columns = layouts[root][1][0]
        return f"{arrays[root]}({index % columns},{index // columns})"

    first = second = pointer = pointer_width = selected = upper = step = mid_length = None
    stack, loops, printing = [], [], []
    emitted, targets = [], set()
    print_start = channel = input_channel = prompt = None
    input_mode = read_pending = get_pending = False
    input_kind = None

    def need(value, ins):
        if value is None:
            raise ValueError(f"missing operand for ${ins.opcode:02X} at ${ins.address:04X}")
        return value

    def emit(address, text):
        emitted.append((address, text))

    def flush(address, newline=False):
        nonlocal print_start
        if printing:
            prefix = "PRINT" + (f"#{channel}," if channel is not None else " ")
            emit(print_start, prefix + ";".join(printing) + ("" if newline else ";"))
            printing.clear()
            print_start = None
        elif newline:
            emit(address, "PRINT" + (f"#{channel}" if channel is not None else ""))

    for ins in code:
        op, arg, address = ins.opcode, ins.argument, ins.address
        if (read_pending or get_pending or input_mode == "store") and not (0x60 <= op < 0x80 or op in (0xf3, 0xf4, 0xff)):
            raise ValueError(f"missing READ/GET/INPUT destination at ${address:04X}")
        boundary = 0x60 <= op < 0x80 or op in (
            0x80, 0xac, 0xaf, 0xb0, 0xb1, 0xb3, 0xca, 0xcd, 0xce, 0xd1, 0xd2,
            0xd3, 0xd4, 0xd5, 0xd8, 0xd9, 0xe2, 0xe3, 0xe5, 0xe6, 0xe8,
            0xe9, 0xeb, 0xf3, 0xf4, 0xf8, 0xf9, 0xff)
        if boundary and not (op == 0x80 and arg in (b"\x06", b"\x08")):
            if op != 0xb3 or not printing:
                flush(address)
        if op < 0x20 or op == 0xfe:
            second = variable(ins)
        elif op < 0x40 or op == 0xfd:
            first = variable(ins)
        elif op < 0x60:
            if op in (0x40, 0x49):
                value = str(int.from_bytes(arg, "little", signed=True))
            elif op in (0x43, 0x4c):
                value = float_literal(arg)
            elif op in (0x52, 0x55):
                value = str(arg[0])
            else:
                value = string_literal(arg[1:])
            if op in (0x40, 0x43, 0x46, 0x52):
                first = value
            else:
                second = value
        elif op < 0x80 or op == 0xff:
            dest = variable(ins)
            if read_pending:
                emit(address, f"READ {dest}")
                read_pending = False
            elif get_pending:
                emit(address, f"GET#{input_channel},{dest}" if input_channel is not None else f"GET {dest}")
                get_pending = False
            elif input_mode == "store":
                if (dest.endswith("$") != (input_kind == "string")):
                    raise ValueError(f"INPUT variable type mismatch at ${address:04X}")
                if input_channel is not None:
                    if prompt:
                        raise ValueError(f"file INPUT has a prompt at ${address:04X}")
                    emit(address, f"INPUT#{input_channel},{dest}")
                else:
                    emit(address, f"INPUT " + (f"{prompt};" if prompt else "") + dest)
                input_mode = prompt = None
                input_kind = None
            else:
                emit(address, f"{dest}={need(first, ins)}")
        elif op in (0x8a, 0x9e, 0x97, 0xab):
            value = "1" if op in (0x8a, 0x97) else "0"
            if op in (0x8a, 0x9e):
                first = value
            else:
                second = value
        elif op in (0x81, 0x82, 0x83, 0x84, 0x85, 0x88, 0x89,
                    0x8b, 0x8c, 0x8d, 0x8f, 0x91, 0x92, 0x93,
                    0x94, 0x95, 0x96, 0x98, 0x99, 0x9b, 0x9d):
            symbol = {0x81: "-", 0x82: "+", 0x83: "*", 0x84: "/", 0x85: "^",
                      0x88: "-", 0x89: "/", 0x8b: ">", 0x8c: "<",
                      0x8d: "AND", 0x8f: "OR", 0x91: "+", 0x92: "+",
                      0x93: "<>", 0x94: "=", 0x95: ">=", 0x96: "<=",
                      0x98: ">", 0x99: "<", 0x9b: "<=", 0x9d: "="}[op]
            left, right = need(second, ins), need(first, ins)
            if op in (0x88, 0x89, 0x92):
                left, right = right, left
            first = f"({left}{symbol}{right})"
        elif op == 0x87:
            first = f"(-{need(first, ins)})"
        elif op == 0x90:
            first = f"(NOT {need(first, ins)})"
        elif op in (0xb5, 0xb6, 0xbb, 0xc2, 0xc3, 0xc4, 0xc5, 0xc6, 0xc7):
            name = {0xb5: "INT", 0xb6: "ABS", 0xbb: "RND", 0xc2: "PEEK",
                    0xc3: "LEN", 0xc4: "STR$", 0xc5: "VAL", 0xc6: "ASC",
                    0xc7: "CHR$"}[op]
            first = f"{name}({need(first, ins)})"
        elif op in (0xdd, 0xde):
            first = f"{'LEFT$' if op == 0xdd else 'RIGHT$'}({need(second, ins)},{need(first, ins)})"
        elif op == 0xe0:
            first = f"MID$({need(first, ins)},{need(second, ins)},1)"
        elif op == 0xa9:
            mid_length = need(first, ins)
        elif op == 0xaa:
            if mid_length is None:
                raise ValueError(f"MID$ length missing at ${address:04X}")
            first = f"MID$({need(first, ins)},{need(second, ins)},{mid_length})"
            mid_length = None
        elif op == 0xf5:
            stack.append(need(first, ins))
        elif op == 0xf6:
            if not stack:
                raise ValueError(f"expression stack underflow at ${address:04X}")
            first = stack.pop()
        elif op == 0xf7:
            if not stack:
                raise ValueError(f"expression stack underflow at ${address:04X}")
            second = stack.pop()
        elif op == 0xce:
            if not stack:
                raise ValueError(f"POKE without address at ${address:04X}")
            emit(address, f"POKE {stack.pop()},{need(first, ins)}")
        elif op == 0xcb:
            upper = need(first, ins)
        elif op == 0xcc:
            step = need(first, ins)
        elif op == 0xcd:
            variable_address = int.from_bytes(arg, "little")
            var = scalar(variable_address)
            if step is not None:
                if not stack:
                    raise ValueError(f"STEP without limit at ${address:04X}")
                upper = stack.pop()
            emit(address, f"FOR {var}={need(first, ins)} TO {need(upper, ins)}"
                 + (f" STEP {step}" if step is not None else ""))
            loops.append((variable_address, var))
            upper = step = None
        elif op in (0xac, 0xd5):
            if op == 0xac:
                loop_addr = int.from_bytes(arg, "big")
                var = scalar(loop_addr)
                if loops and loops[-1][0] == loop_addr:
                    loops.pop()
                emit(address, f"NEXT {var}")
            else:
                if loops:
                    loops.pop()
                emit(address, "NEXT")
        elif op == 0xfc:
            selected = int.from_bytes(arg, "little")
        elif op in (0x9f, 0xa0, 0xa2, 0xa3):
            if selected is None or selected not in layouts and selected not in aliases:
                raise ValueError(f"array access without base at ${address:04X}")
            width = layouts[aliases[selected][0] if selected in aliases else selected][0]
            if width != (5 if op in (0x9f, 0xa0) else 2):
                raise ValueError(f"array element type mismatch at ${address:04X}")
            element = indexed(selected, need(first, ins))
            if op in (0x9f, 0xa2):
                first = element
            else:
                pointer = element
                pointer_width = width
        elif op in (0xa1, 0xa8):
            if selected not in layouts or len(layouts[selected][1]) != 2:
                raise ValueError(f"two-dimensional access without descriptor at ${address:04X}")
            element = f"{arrays[selected]}({need(second, ins)},{need(first, ins)})"
            if op == 0xa1:
                first = element
            else:
                pointer = element
                pointer_width = layouts[selected][0]
        elif op in (0xf8, 0xf9):
            if pointer is None:
                raise ValueError(f"array store without index at ${address:04X}")
            emit(address, f"{pointer}={need(first, ins)}")
        elif op in (0xf3, 0xf4):
            dest = direct(int.from_bytes(arg, "little"), 5 if op == 0xf3 else 2)
            if read_pending:
                emit(address, f"READ {dest}")
                read_pending = False
            else:
                emit(address, f"{dest}={need(first, ins)}")
        elif op in (0xed, 0xf0):
            value = direct(int.from_bytes(arg, "little"), 5)
            if op == 0xed:
                second = value
            else:
                first = value
        elif op in (0xd1, 0xd2, 0xd4):
            target = address + arg[0] + 1 if op == 0xd4 else int.from_bytes(arg, "little")
            targets.add(target)
            prefix = f"IF ({need(first, ins)})=0 THEN GOTO " if op == 0xd4 else "GOTO " if op == 0xd1 else "GOSUB "
            emit(address, prefix + f"@{target:04X}")
        elif op == 0xe2:
            targets.update(arg)
            emit(address, f"ON {need(first, ins)} GOTO " + ",".join(f"@{target:04X}" for target in arg))
        elif op == 0xd8:
            emit(address, "RETURN")
        elif op == 0xd3:
            emit(address, "END")
        elif op == 0xca:
            emit(address, "RUN")
        elif op == 0xd9:
            if arg:
                if pointer is None or arg[0] != (0x41 if pointer_width == 5 else 0x42):
                    raise ValueError(f"READ selector without matching array at ${address:04X}")
                emit(address, f"READ {pointer}")
            else:
                read_pending = True
        elif op == 0xeb:
            emit(address, "RESTORE")
        elif op == 0xb3:
            input_mode = True
            if printing:
                prompt = ";".join(printing)
                printing.clear()
                print_start = None
        elif op in (0xd6, 0xd7):
            if not input_mode:
                raise ValueError(f"INPUT without mode at ${address:04X}")
            input_mode = "store"
            input_kind = "string" if op == 0xd7 else "numeric"
        elif op == 0xdc:
            get_pending = True
        elif op == 0x80:
            if arg[0] >= 18:
                raise ValueError(f"unknown system selector ${arg[0]:02X} at ${address:04X}")
            system_handler = image.word(0x19ba + 2 * arg[0])
            if system_handler == 0x25bb:
                first = "TI"
            elif system_handler == 0x25ee:
                first = "TI$"
            elif system_handler == 0x2626:
                emit(address, f"TI$={need(first, ins)}")
            else:
                raise ValueError(f"untranslated system handler ${system_handler:04X} at ${address:04X}")
        elif op in (0xd0, 0xcf, 0xe7):
            if not printing:
                print_start = address
            printing.append(f"SPC({need(first, ins)})" if op == 0xe7 else need(first, ins))
        elif op == 0xec:
            flush(address, newline=True)
        elif op == 0xe5:
            channel = need(first, ins)
        elif op == 0xe6:
            input_channel = need(first, ins)
        elif op == 0xe9:
            flush(address)
            channel = input_channel = None
        elif op == 0xaf:
            if len(stack) < 2:
                raise ValueError(f"OPEN without arguments at ${address:04X}")
            device, number = stack.pop(), stack.pop()
            emit(address, f"OPEN {number},{device},{need(first, ins)}")
        elif op == 0xb0:
            if len(stack) < 3:
                raise ValueError(f"OPEN without arguments at ${address:04X}")
            secondary, device, number = stack.pop(), stack.pop(), stack.pop()
            emit(address, f"OPEN {number},{device},{secondary},{need(first, ins)}")
        elif op == 0xb1:
            emit(address, f"CLOSE {need(first, ins)}")
        elif op == 0xe8:
            emit(address, f"SYS {need(first, ins)}")
        elif op == 0xe3:
            if not stack:
                raise ValueError(f"WAIT without address at ${address:04X}")
            emit(address, f"WAIT {stack.pop()},{need(first, ins)}")
        else:
            raise ValueError(f"untranslated handler ${op:02X} at ${address:04X}")

    if stack or read_pending or get_pending or input_mode or upper is not None or step is not None:
        raise ValueError("unfinished Speedcode expression or statement")
    flush(image.sections[4])
    positions = {ins.address for ins in code}
    if not targets <= positions:
        raise ValueError(f"branch into operand at ${min(targets - positions):04X}")
    locations = {}
    for target in targets:
        index = next((i for i, (address, _) in enumerate(emitted) if address >= target), None)
        if index is None:
            raise ValueError(f"branch without BASIC statement at ${target:04X}")
        locations[target] = (len(dimensions) + index + 1) * 10
    lines = []
    for index, text in enumerate(dimensions + [statement for _, statement in emitted], 1):
        for target, number in locations.items():
            text = text.replace(f"@{target:04X}", str(number))
        body = tokenize(text)
        if index * 10 >= 50000 or len(body) > 250:
            raise ValueError("BASIC program exceeds line limits")
        lines.append(BasicLine(index * 10, body))
    return lines
