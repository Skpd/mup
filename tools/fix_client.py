"""
Fixes the 0.97 client's data files (docs/protocol-097.md, Extending the client), keeping FILE.orig the first time:

- Data/Local/Text.bmd: entries 419 and 429 hold a %s the client formats without an argument (the trade and guild
  questions crash), entry 0 is the font face of all text (empty: wine picks one).
- Data/Local/item.bmd, skill.bmd, Quest.bmd: names the Chinese translation left in Korean (the second class sets
  and weapons, the quest items, an orb, a skill, quest 0), shown as garbage. They get the English names of the
  server's data/Item.txt and data/Skill.txt. item.bmd and skill.bmd end in a checksum the client checks ("File
  corrupted"), written again.

usage: python3 tools/fix_client.py [client dir] [--font FACE]    (default ~/projects/client/mu, Verdana)
"""
import shlex
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY = b'\xFC\xCF\xAB'  # restarts at every record
TEXT_ENTRY = 300
TEXTS = {
    419: 'would like to trade with you.',  # trade question, dialog 121 (0x4c91d1): the name is its first line
    429: 'wants to join your guild.',  # guild join question, dialog 119 (0x4c95be)
}
FONT = 0  # Text.bmd entry with the face name of CreateFontA (0x40f2c0)
ITEMS, ITEM_RECORD, ITEM_NAME = 512, 56, 30
SKILLS, SKILL_RECORD, SKILL_NAME = 64, 38, 32
QUESTS, QUEST_RECORD, QUEST_NAME = 200, 584, (6, 38)
QUEST_NAMES = {0: "Find the 'Scroll of Emperor'!"}  # Korean in the client
# file -> checksum key of the 4 bytes after the records (client 0x45a100, 0x4596e0)
CHECKSUM_KEYS = {'item.bmd': 0xE2F1, 'skill.bmd': 0x5A18}


def xor(data):
    return bytes(b ^ KEY[i % 3] for i, b in enumerate(data))


def checksum(data, key):
    """The client's checksum (0x4584c0) of the file's records as stored (xored): 4 byte words, little endian."""
    acc = key << 9
    for i in range(0, len(data) - 3, 4):
        word = int.from_bytes(data[i:i + 4], 'little')
        n = i >> 2
        acc = acc ^ word if (n + key) & 1 == 0 else (acc + word) & 0xFFFFFFFF
        if i & 0xF == 0:
            acc ^= ((acc + key) & 0xFFFFFFFF) >> ((n & 7) + 1)
    return acc


def backup(path):
    orig = path.with_name(path.name + '.orig')
    if not orig.exists():
        shutil.copyfile(path, orig)


def rename(path, record, count, start, size, names):
    """Replaces the non ASCII names of the records with the names given by record index. Returns the changes."""
    data = bytearray(path.read_bytes())
    changes = []
    for n in range(count):
        r = bytearray(xor(data[n * record:(n + 1) * record]))
        old = bytes(r[start:start + size]).split(b'\0', 1)[0]
        new = names.get(n)
        if not old or old.isascii() or new is None:
            continue
        raw = new.encode('latin-1')[:size - 1]
        r[start:start + size] = raw.ljust(size, b'\0')
        data[n * record:(n + 1) * record] = xor(r)
        changes.append((n, old.decode('cp949', 'replace'), raw.decode('latin-1')))
    key = CHECKSUM_KEYS.get(path.name)
    end = record * count
    if key is not None and data[end:end + 4] != checksum(data[:end], key).to_bytes(4, 'little'):
        data[end:end + 4] = checksum(data[:end], key).to_bytes(4, 'little')
        changes.append(('checksum', '', data[end:end + 4].hex(' ')))
    if changes:
        backup(path)
        path.write_bytes(data)
    return changes


def texts(path, font):
    """Text.bmd: the entries of TEXTS and the font face. 300 byte records, a multiple of 3, so one key run."""
    data = bytearray(path.read_bytes())
    changes = []
    for n, text in {**TEXTS, FONT: font}.items():
        old = xor(data[n * TEXT_ENTRY:(n + 1) * TEXT_ENTRY]).split(b'\0', 1)[0].decode('latin-1')
        if old != text:
            data[n * TEXT_ENTRY:(n + 1) * TEXT_ENTRY] = xor(text.encode('latin-1').ljust(TEXT_ENTRY, b'\0'))
            changes.append((n, old, text))
    if changes:
        backup(path)
        path.write_bytes(data)
    return changes


def server_names(path):
    """Skill number -> name of a later server's Skill.txt, or item type -> name of its Item.txt."""
    names = {}
    group = None
    with open(path, encoding='latin-1') as f:
        for line in f:
            v = shlex.split(line.split('//', 1)[0])
            if not v:
                continue
            if path.name == 'Skill.txt':
                if v[0] != 'end':
                    names[int(v[0])] = v[1]
            elif v[0] == 'end':
                group = None
            elif group is None:
                group = int(v[0])
            elif int(v[0]) < 32:
                names[group * 32 + int(v[0])] = v[8]
    return names


def main(argv):
    args = [a for a in argv[1:] if not a.startswith('--')]
    font = argv[argv.index('--font') + 1] if '--font' in argv else 'Verdana'
    if '--font' in argv:
        args.remove(font)
    local = Path(args[0] if args else Path.home() / 'projects/client/mu') / 'Data' / 'Local'
    if not (local / 'Text.bmd').exists():
        print('no Data/Local/Text.bmd in', local.parent.parent)
        return 1
    found = {
        'Text.bmd': texts(local / 'Text.bmd', font),
        'item.bmd': rename(local / 'item.bmd', ITEM_RECORD, ITEMS, 0, ITEM_NAME,
                           server_names(ROOT / 'data/Item.txt')),
        'skill.bmd': rename(local / 'skill.bmd', SKILL_RECORD, SKILLS, 0, SKILL_NAME,
                            server_names(ROOT / 'data/Skill.txt')),
        'Quest.bmd': rename(local / 'Quest.bmd', QUEST_RECORD, QUESTS, QUEST_NAME[0], QUEST_NAME[1] - QUEST_NAME[0],
                            QUEST_NAMES),
    }
    for name, changes in found.items():
        for n, old, new in changes:
            print('{} {}: {!r} -> {!r}'.format(name, n, old, new))
        if not changes:
            print('{}: nothing to change'.format(name))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
