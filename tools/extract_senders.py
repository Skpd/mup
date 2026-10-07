"""
Lists the client -> server packets built in decompiled sender functions (DumpSenders.java output).

The client builds packets with a stream helper, in two styles:
    AddData(&type, 1, 0)        type is 0xC1 / 0xC2
    AddData(&size, 1 or 2, 0)   size placeholder
    AddData(&head, 1, 0)
or with the init inlined:
    buf[0] = 0xC1; len = 2
    AddData(&head, 1, 0)
then
    AddData(&value, n, xor)...  fields, sub code first
or appended inline: buf[len] = value; XorRange(len, len + 1, 1)
or with AddData itself inlined: *(undefined4 *)((int)&buf + len) = value; ... xor loop
Every packet is sent right after it's built, so a packet is everything appended since the previous send.
Header bytes are appended without the xor flag and fields (sub code first) with it,
so the head is the last header append before the first field.
Sending encrypted rewrites the header to 0xC3 / 0xC4, that marks the packet as encrypted.

usage: python3 extract_senders.py senders.c [add data function] [xor range function]
"""
import re
import sys
from collections import OrderedDict

ADD_DATA = 'FUN_00403390'
XOR_RANGE = 'FUN_00403290'
SEND = 'Ordinal_19('

FUNC_RE = re.compile(r'^// ===== (\S+) @ (\S+)')
ASSIGN_RE = re.compile(r'^\s*(\w+)(?:\[\d+\])?(?:\._\d+_\d+_)? = (.+);$')
ADD_RE = re.compile(r'%s\((?:\([^)]*\))?&?(\w+)(?:\[\d+\])?,([^,]+),(\w+)\)' % ADD_DATA)
INLINE_RE = re.compile(r'^\s*\(&\w+\)\[\w+\] = (.+);$')
# stores relative to the buffer and its current length, the type gives the size
STORE_RE = re.compile(r'^\s*\*\((\w+) \*\)\(\(int\)&?\w+ \+ \w+\) = (.+);$')
STORE_SIZES = {'undefined1': 1, 'byte': 1, 'char': 1, 'undefined2': 2, 'short': 2, 'ushort': 2,
               'undefined4': 4, 'int': 4, 'uint': 4, 'float': 4, 'undefined8': 8}
CONST_RE = re.compile(r'(?:^|[,(\s])(0x[0-9a-f]+|[1-9]\d*|0)\)?$')


def constant(expr):
    """Last constant in an assignment like CONCAT31(x,0xc1) or 0x1d."""
    m = CONST_RE.search(expr.strip())
    return int(m.group(1), 0) if m else None


def parse(path):
    packets = []
    func = None
    values = {}
    current = None
    last_type = None
    pending_inline = None

    def packet():
        nonlocal current
        if current is None:
            current = {'func': func, 'type': last_type or 0xC1, 'header': [], 'head': None, 'fields': [],
                       'encrypted': False}
        return current

    def start_fields():
        if current['head'] is None and current['header']:
            current['head'] = current['header'][-1]

    def finish():
        nonlocal current, last_type
        if current:
            start_fields()
            if current['head'] is not None:
                packets.append(current)
        current = None
        last_type = None

    for line in open(path, encoding='latin-1'):
        m = FUNC_RE.match(line)
        if m:
            finish()
            func = m.group(2)
            values = {}
            continue

        if SEND in line:
            finish()
            continue

        m = ASSIGN_RE.match(line)
        if m:
            var, value = m.group(1), m.group(2)
            values[var] = value
            c = constant(value)
            if c in (0xC1, 0xC2) and (current is None or current['head'] is None):
                last_type = c
                if current:
                    current['type'] = c
            elif c in (0xC3, 0xC4) and current:
                current['encrypted'] = True

        m = STORE_RE.match(line)
        if m and m.group(1) in STORE_SIZES:
            packet()
            start_fields()
            current['fields'].append((str(STORE_SIZES[m.group(1)]), m.group(2)))
            continue

        m = INLINE_RE.match(line)
        if m:
            pending_inline = m.group(1)
            continue
        if pending_inline is not None and XOR_RANGE in line:
            packet()
            start_fields()
            current['fields'].append(('1', pending_inline))
        if XOR_RANGE in line or not line.strip():
            pending_inline = None

        for var, size, xor in ADD_RE.findall(line):
            value = values.get(var, '?')
            p = packet()
            if xor == '0' and p['head'] is None:
                p['header'].append(constant(value))
            else:
                start_fields()
                p['fields'].append((size.strip(), value))

    finish()
    return packets


def main():
    packets = parse(sys.argv[1])
    seen = OrderedDict()
    for p in packets:
        sub = None
        fields = p['fields']
        if p['head'] in (0xF1, 0xF3, 0xF4, 0x0E, 0x41, 0x42, 0x43) and fields and fields[0][0] == '1':
            sub = constant(fields[0][1])
        typ = p['type'] + (2 if p['encrypted'] else 0)
        key = (p['head'], sub, typ, tuple(fields))
        seen.setdefault(key, []).append(p['func'])

    for (head, sub, typ, fields), funcs in sorted(seen.items(), key=lambda kv: (kv[0][0] or 0, kv[0][1] or 0)):
        code = '%02X' % head if head is not None else '??'
        if sub is not None:
            code += ' %02X' % sub
        print('%02X %s  from %s' % (typ, code, ', '.join(sorted(set(funcs)))))
        offset = 3 if typ in (0xC1, 0xC3) else 4  # type, size (2 bytes for C2/C4), head
        for n, expr in fields:
            print('    [%s] %s bytes: %s' % (offset, n, expr))
            offset = offset + int(n) if n.isdigit() and offset != '?' else '?'


if __name__ == '__main__':
    main()
