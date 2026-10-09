"""
Reads and changes the client's Data/Local/Text.bmd: 300 byte entries xored with FC CF AB (see Extending the client
in docs/protocol-097.md).

usage: python3 tools/text_bmd.py FILE get N...
       python3 tools/text_bmd.py FILE set N TEXT     keeps FILE.orig the first time
The known fixes of the client's texts are in tools/fix_client.py.
"""
import shutil
import sys
from pathlib import Path

ENTRY = 300
KEY = b'\xFC\xCF\xAB'


def xor(data, start):
    return bytes(b ^ KEY[(start + i) % 3] for i, b in enumerate(data))


def get(data, n):
    return xor(data[n * ENTRY:(n + 1) * ENTRY], n * ENTRY).split(b'\0', 1)[0].decode('latin-1')


def put(data, n, text):
    raw = text.encode('latin-1')
    if len(raw) >= ENTRY:
        raise ValueError('{} bytes, an entry holds {}'.format(len(raw), ENTRY - 1))
    data[n * ENTRY:(n + 1) * ENTRY] = xor(raw.ljust(ENTRY, b'\0'), n * ENTRY)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    path, command = Path(argv[1]), argv[2]
    data = bytearray(path.read_bytes())
    if command == 'get':
        for n in argv[3:]:
            print(n, repr(get(data, int(n))))
        return 0
    if command != 'set' or len(argv) != 5:
        print(__doc__)
        return 2
    changes = {int(argv[3]): argv[4]}
    backup = path.with_name(path.name + '.orig')
    if not backup.exists():
        shutil.copyfile(path, backup)
    for n, text in changes.items():
        print('{}: {!r} -> {!r}'.format(n, get(data, n), text))
        put(data, n, text)
    path.write_bytes(data)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
