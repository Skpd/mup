"""
Lists the packet bytes each server -> client handler reads, from decompiled handlers (DumpDecompiled.java output)
and the dispatch map (ReceiveDispatch.java output).

Handlers get the packet as their first parameter, so fields show up as reads relative to param_1:
    *(byte *)(param_1 + 5)   *(undefined2 *)(param_1 + 6)   param_1[4]   (char *)(param_1 + 9)
Reads through other pointers (list entries, aliases) are not followed, check the code for those.

usage: python3 extract_handlers.py receive.txt handlers.c
"""
import re
import sys

DISPATCH_RE = re.compile(r'^\s*([0-9A-F]{2}(?: [0-9A-F]{2})*) @ (\w+) calls \[(.*)\]')
FUNC_RE = re.compile(r'^// ===== (\S+) @ (\S+)')
SIZES = {'byte': 1, 'char': 1, 'undefined1': 1, 'bool': 1,
         'short': 2, 'ushort': 2, 'undefined2': 2, 'word': 2,
         'int': 4, 'uint': 4, 'undefined4': 4, 'float': 4, 'dword': 4, 'long': 4, 'ulong': 4}

# *(type *)(param_1 + 0x10)  /  *(type *)param_1
TYPED_RE = re.compile(r'\*\((\w+) \*\)\(?param_1(?: \+ (0x[0-9a-f]+|\d+))?\)?')
# param_1[5] on a byte pointer
INDEX_RE = re.compile(r'param_1\[(0x[0-9a-f]+|\d+)\]')
# param_1 + 9 used as a pointer (strings, copied blocks)
POINTER_RE = re.compile(r'(?<![\w*(])\(?(?:\(\w+ \*\))?param_1 \+ (0x[0-9a-f]+|\d+)\)?(?!\))')


def handler_reads(path):
    reads = {}
    func = None
    for line in open(path, encoding='latin-1'):
        m = FUNC_RE.match(line)
        if m:
            func = m.group(2).lstrip('0')
            reads[func] = {}
            continue
        if func is None:
            continue
        found = reads[func]
        for typ, off in TYPED_RE.findall(line):
            off = int(off, 0) if off else 0
            found[off] = max(found.get(off, 0), SIZES.get(typ, 0)) or found.get(off, 0) or '?'
        for off in INDEX_RE.findall(line):
            found.setdefault(int(off, 0), 1)
        for off in POINTER_RE.findall(line):
            found.setdefault(int(off, 0), 'ptr')
    return reads


def main():
    reads = handler_reads(sys.argv[2])
    for line in open(sys.argv[1]):
        m = DISPATCH_RE.match(line)
        if not m:
            continue
        code, _, calls = m.groups()
        handlers = [c.split('@')[1].lstrip('0') for c in calls.split(', ') if '@' in c]
        print(code)
        for h in handlers:
            if h in reads and reads[h]:
                fields = ', '.join('%d:%s' % (off, size) for off, size in sorted(reads[h].items()))
                print('    %s reads %s' % (h, fields))


if __name__ == '__main__':
    main()
