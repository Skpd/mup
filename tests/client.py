"""
Scripted 0.97 client: starts the connect and game server, then plays them over real sockets the way the
client does (same keys, encryption, xor and packet layouts, see docs/protocol-097.md) and checks the answers.

usage: ./venv/bin/python tests/client.py
Exits non zero on the first failed check and prints the end of the server logs.
The servers run with their own config on ports 44415 and 55911, a database in a temporary directory and their own
monsters (MONSTERS, SPAWNS, DROPS), so the test can run next to the usual servers.
"""
import os
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
from collections import deque
from types import SimpleNamespace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mup.common.crypt import Crypt  # noqa: E402
from mup.packet.base import Base  # noqa: E402
from mup.packet.server import SDamage  # noqa: E402

HOST = '127.0.0.1'
CS_PORT = 44415
GS_PORT = 55911
PERSONAL_CODE = '4321'
CONFIG = """
[network]
cs_port = {cs_port}
gs_port = {gs_port}
gs_host = {host}
[database]
db_path = {db}
autosave_interval = 2
[world]
monster_info = {monsters}
monster_spawns = {spawns}
item_drops = {drops}
[accounts]
personal_code = {code}
[log]
log_level = DEBUG
log_packets = yes
"""
# test monsters, Monster.txt columns: index rate name level life mana damage_min damage_max defense magic_defense
# attack_rate defense_rate move_range attack_type attack_range view_range move_speed attack_speed regen_time ...
# The dragon and the hound always hit (attack rate 1000), nothing misses the spider (defense rate 0)
MONSTERS = """
2 1 "Budge Dragon" 4 5 0 1 1 0 0 1000 0 0 0 1 5 300 500 10 2 0 0 0 0 0 0 0 0
3 1 "Spider" 2 100 0 4 7 0 0 0 0 0 0 1 0 400 1800 1 2 0 0 0 0 0 0 0 0
5 1 "Hell Hound" 38 1400 0 500 500 0 0 1000 0 0 0 1 5 300 500 10 2 0 0 0 0 0 0 0 0
26 1 "Goblin" 3 1000 0 1 1 0 0 0 0 0 0 1 0 400 1800 10 2 0 0 0 0 0 0 0 0
7 1 "Dodger" 3 1000 0 1 1 0 0 0 100000 0 0 1 0 400 1800 10 2 0 0 0 0 0 0 0 0
end
"""
# MonsterSetBase single monsters (type, map, leash, x, y, direction), each appears within 3 tiles of its spot:
# a spider that doesn't look (view range 0) at the east exit of Lorencia, a dragon hitting 1 north east of it, a hound
# killing with one hit at the west exit, two goblins with much life south east of the spider for the area skills and
# a monster nearly nothing hits (defense rate 100000) with them. None of them wanders (move range 0)
SPIDER_SPOT = (182, 126)
DRAGON_SPOT = (200, 100)
HOUND_SPOT = (90, 128)
GOBLIN_SPOT = (190, 140)
SPAWNS = """
2
003 00 30 {} {} -1
002 00 30 {} {} -1
005 00 30 {} {} -1
026 00 30 {} {} -1
026 00 30 {} {} -1
007 00 30 {} {} -1
end
""".format(*SPIDER_SPOT, *DRAGON_SPOT, *HOUND_SPOT, *GOBLIN_SPOT, *GOBLIN_SPOT, *GOBLIN_SPOT)

# fixed drops (monster type, item group, index, level, count, chance): every spider leaves a short sword, a small
# healing potion and 30 zen. The test monsters have no random drops (ItemRate, MoneyRate 0)
DROPS = """
3 0 1 0 0 100
3 14 1 0 0 100
3 14 15 0 30 100
"""
# item bytes: type & 0xFF, skill << 7 | level << 3 | luck << 2 | option, durability, type bit 8 << 7 | excellent
SWORD = bytes([0x01, 0x00, 22, 0x00])  # 0/1, durability 22
POTION = bytes([0xC1, 0x00, 1, 0x80])  # 14/1: type 0x1C1, one potion
ZEN_TYPE = 0x1CF
NO_EQUIPMENT = bytes([0xFF] * 5 + [0, 0, 0, 0xF8, 0])

ATTACK_PAUSE = 0.4  # seconds between attacks, the server's pace at speed 0 (mup.server.combat.ATTACK_INTERVAL)

# x, y step of each walk direction
STEPS = [(-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0)]
# start areas: Lorencia gate 17, Noria gate 27 for elves (the client's Gate.bmd)
LORENCIA = (0, range(133, 152), range(118, 136))
NORIA = (3, range(171, 178), range(108, 118))
# gate 23 in Lorencia leads to gate 24 in Noria, from level 10
NORIA_GATE = (23, range(213, 218), range(246, 248))
NORIA_ARRIVAL = (3, range(148, 156), range(5, 7), 5)
# where A and B stand for the tests in view: outside the east exit of Lorencia, next to the spider (x 179..185,
# y 123..129). The walks from here stay on walkable tiles outside the safe zone
A_SPOT = (180, 127)
B_SPOT = (178, 126)
# Lorencia terrain, the client's file: 3 byte header, then y * 256 + x. 0x04 wall, 0x08 no ground, 0x01 safe zone
TERRAIN = (ROOT / 'data/terrain/Terrain1.att').read_bytes()[3:]
# create class (class number << 2) -> str, agi, vit, ene, life, mana (DefaultClassInfo.txt)
CLASS_STATS = {0: (18, 18, 15, 30, 60, 60), 16: (28, 20, 25, 10, 110, 20), 32: (22, 25, 20, 15, 80, 30)}
# character info [4..41]
INFO_FIELDS = ('x', 'y', 'map', 'dir', 'exp', 'next_exp', 'points', 'str', 'agi', 'vit', 'ene', 'life', 'max_life',
               'mana', 'max_mana', 'money', 'pk', 'ctl')


class ClientCrypt(Crypt):
    """Client side keys. Login fields are xored by build() before the xor chain, not by encrypt()."""

    def encrypt_login(self, buff, start, length=10):
        pass


class Conn:
    def __init__(self, port, name):
        self.name = name
        self.s = socket.create_connection((HOST, port), timeout=3)
        self.buf = bytearray()
        self.joined = False
        self.cid = None
        self.crypt = ClientCrypt(encode_keys=str(ROOT / 'data/Enc1.dat'), decode_keys=str(ROOT / 'data/Dec2.dat'))
        self.crypt.do_extract = False  # the server doesn't xor what it sends
        self.inbox = []

    def send_raw(self, data):
        self.s.sendall(bytes(data))

    def build(self, data, encrypt=False):
        """Packet as the client sends it: login fields xored, fields xor chained, optionally C3/C4 encrypted."""
        p = Base(bytearray(data))
        p.length = len(p)
        if p.head == 0xF1 and p.sub == 0x01:
            for start in (4, 14):
                for i in range(10):
                    p[start + i] ^= Crypt.login_keys[i % 3]
        if encrypt:
            self.crypt.pack(p, p.is_double())
            return self.crypt.encrypt(p)
        if self.joined:
            self.crypt.pack(p, p.is_double())
        return p

    def send(self, data, encrypt=False):
        self.send_raw(self.build(data, encrypt))

    def _read_packet(self, timeout):
        """Next packet, C3/C4 decrypted. .encrypted tells how it arrived."""
        self.s.settimeout(timeout)
        while True:
            if self.buf:
                header = 3 if self.buf[0] in (0xC2, 0xC4) else 2
                if len(self.buf) >= header:
                    size = (self.buf[1] << 8 | self.buf[2]) if header == 3 else self.buf[1]
                    if len(self.buf) >= size:
                        p = Base(self.buf[:size])
                        del self.buf[:size]
                        encrypted = p[0] in (0xC3, 0xC4)
                        if encrypted:
                            p = self.crypt.decrypt(p)
                        p.encrypted = encrypted
                        return p
            chunk = self.s.recv(65536)
            if not chunk:
                raise EOFError(self.name + ' closed')
            self.buf += chunk

    def recv_until(self, pred, timeout=3.0, what=''):
        """First packet matching pred, packets read on the way are kept for later calls."""
        deadline = time.time() + timeout
        for i, p in enumerate(self.inbox):
            if pred(p):
                return self.inbox.pop(i)
        while True:
            left = deadline - time.time()
            if left <= 0:
                raise AssertionError('{}: timed out waiting for {}; last packets {}'.format(
                    self.name, what, [x.hex(' ') for x in self.inbox[-8:]]))
            try:
                p = self._read_packet(left)
            except socket.timeout:
                continue
            if pred(p):
                return p
            self.inbox.append(p)


def key(head, sub=None):
    def pred(p):
        return p.head == head and (sub is None or p.sub == sub)
    return pred


def of(head, cid, at=3):
    """Packet with the given head carrying cid (2 bytes BE) at offset at."""
    def pred(p):
        return p.head == head and (p[at] << 8 | p[at + 1]) & 0x7FFF == cid
    return pred


# list packets: offset of the count, of the first entry, entry size
LISTS = {0x12: (4, 5, 32), 0x13: (4, 5, 12), 0x14: (3, 4, 2), 0x1F: (4, 5, 22)}


def entries(p):
    """Entries of a 12 / 13 / 14 / 1F list packet."""
    count_at, start, size = LISTS[p.head]
    return [p[start + i * size:start + (i + 1) * size] for i in range(p[count_at])]


def entry(p, cid):
    """The entry for cid of a list packet, the cid is its first 2 bytes."""
    return next(e for e in entries(p) if (e[0] << 8 | e[1]) & 0x7FFF == cid)


def meet(conn, monster_type, count=1):
    """(cid, (x, y)) of the first count monsters of a type in the 13 packets conn gets."""
    found = []
    while len(found) < count:
        p = conn.recv_until(lambda p: p.head == 0x13 and any(e[2] == monster_type for e in entries(p)),
                            what='monster type {}'.format(monster_type))
        found += [((e[0] << 8 | e[1]) & 0x7FFF, (e[6], e[7])) for e in entries(p) if e[2] == monster_type]
    return found[:count]


def inventory(conn):
    """Slot -> item bytes of the next F3 10."""
    p = conn.recv_until(key(0xF3, 0x10), what='inventory')
    return {p[6 + i * 5]: bytes(p[7 + i * 5:11 + i * 5]) for i in range(p[5])}


def skill_change(conn):
    """(change, slot, skill) of the next F3 11 with FE / FF."""
    p = conn.recv_until(lambda p: key(0xF3, 0x11)(p) and p[4] in (0xFE, 0xFF), what='skill change')
    return p[4], p[5], p[6]


def notice(conn, message):
    """Waits for a notice (0D) with message, the ones before it stay in the inbox."""
    conn.recv_until(lambda p: p.head == 0x0D and text(p[4:]) == message, what='notice ' + message)
    return True


def listed(head, cid):
    """12 / 13 / 14 list packet with an entry for cid."""
    def pred(p):
        return p.head == head and any((e[0] << 8 | e[1]) & 0x7FFF == cid for e in entries(p))
    return pred


def item_type(item):
    return item[0] | (item[3] >> 7) << 8


def ground_entries(p):
    """Entries of a 20 packet as dicts: id, dropped flag, x, y, and the item bytes or the zen amount. Zen entries
    are 9 bytes, the amount around the type bytes."""
    found = []
    at = 5
    for _ in range(p[4]):
        raw_id = p[at] << 8 | p[at + 1]
        e = {'id': raw_id & 0x7FFF, 'dropped': bool(raw_id & 0x8000), 'x': p[at + 2], 'y': p[at + 3]}
        item = bytes(p[at + 4:at + 8])
        if item_type(item) == ZEN_TYPE:
            e['zen'] = item[1] << 16 | item[2] << 8 | p[at + 8]
            at += 9
        else:
            e['item'] = item
            at += 8
        found.append(e)
    check(at == len(p), '20 entries fill the packet: ' + p.hex(' '))
    return found


def collect_drops(conn, count, what):
    """The next count ground items conn is shown (20 packets)."""
    found = []
    while len(found) < count:
        found += ground_entries(conn.recv_until(key(0x20), what=what))
    return found


def gone_ids(p):
    """Item ids of a 21 packet: C2, count at [4], 2 bytes each."""
    return [p[5 + i * 2] << 8 | p[6 + i * 2] for i in range(p[4])]


def item_gone(conn, item_id, what):
    conn.recv_until(lambda p: p.head == 0x21 and item_id in gone_ids(p), what=what)


def pick_up(conn, item_id):
    """C3 22 pick up, returns the 22 result."""
    conn.send([0xC1, 0, 0x22, item_id >> 8, item_id & 0xFF], encrypt=True)
    p = conn.recv_until(key(0x22), what='pick up result')
    check(len(p) == 8, 'pick up result is 8 bytes: ' + p.hex(' '))
    return p


def move_item(conn, source, item, target):
    """C3 24 move within the inventory, returns the C3 24 result."""
    conn.send([0xC1, 0, 0x24, 0, source, *item, 0, target], encrypt=True)
    p = conn.recv_until(key(0x24), what='move result')
    check(p.encrypted and len(p) == 9, 'move result is C3, 9 bytes: ' + p.hex(' '))
    return p


def exp16(p):
    """The exp of a 16 kill packet, 2 bytes BE."""
    return p[5] << 8 | p[6]


def name10(s):
    return list(s.encode().ljust(10, b'\0'))


def text(data):
    return bytes(data).split(b'\0', 1)[0].decode()


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print('  ok -', msg)


def walk(x, y, steps, direction):
    """walk request: start x y, direction << 4 | step count, then one step direction per nibble"""
    path = []
    for i in range(0, len(steps), 2):
        path.append(steps[i] << 4 | (steps[i + 1] if i + 1 < len(steps) else 0))
    return [0xC1, 0, 0x10, x, y, direction << 4 | len(steps), *path]


def walkable(x, y):
    return 0 <= x < 256 and 0 <= y < 256 and not TERRAIN[y * 256 + x] & 0x0C


def find_path(start, target):
    """Shortest walkable path in Lorencia from start to target, the tiles after start."""
    came = {start: None}
    todo = deque([start])
    while todo:
        tile = todo.popleft()
        if tile == target:
            path = []
            while tile != start:
                path.append(tile)
                tile = came[tile]
            return path[::-1]
        for dx, dy in STEPS:
            n = tile[0] + dx, tile[1] + dy
            if n not in came and walkable(*n):
                came[n] = tile
                todo.append(n)
    raise AssertionError('no path from {} to {}'.format(start, target))


def walk_path(conn, start, target):
    """Walks around the walls from start to target in walks of 15 steps, returns target."""
    x, y = start
    steps = []
    for tx, ty in find_path(start, target):
        steps.append(STEPS.index((tx - x, ty - y)))
        x, y = tx, ty
    x, y = start
    for i in range(0, len(steps), 15):
        part = steps[i:i + 15]
        conn.send(walk(x, y, part, part[-1]))
        for d in part:
            x, y = x + STEPS[d][0], y + STEPS[d][1]
    return target


def near_tile(spot, distance):
    """A walkable tile in Lorencia, outside the safe zone, distance tiles south of spot or around it."""
    x, y = spot
    for dx, dy in [(0, distance), (distance, 0), (-distance, 0), (0, -distance), (distance, distance)]:
        if walkable(x + dx, y + dy) and not TERRAIN[(y + dy) * 256 + x + dx] & 0x01:
            return x + dx, y + dy
    raise AssertionError('nothing walkable {} tiles from {}'.format(distance, spot))


def drain(conn, seconds):
    """Reads what arrives for a while into the inbox."""
    try:
        conn.recv_until(lambda p: False, timeout=seconds)
    except AssertionError:
        pass


def chat(name, message):
    return [0xC1, 0, 0x00, *name10(name), *message.encode(), 0]


def chat_round_trip(conn, name):
    """Chat comes back to the sender: everything sent before it has been handled."""
    conn.send(chat(name, 'ping'))
    conn.recv_until(lambda p: p.head == 0x00 and text(p[3:13]) == name, what='own chat')


def life_value(p):
    """Value of a 26 / 27 life or mana packet, [4..5] big endian."""
    return p[4] << 8 | p[5]


def in_area(info, area):
    map_id, xs, ys = area
    return info['map'] == map_id and info['x'] in xs and info['y'] in ys


def damage(p):
    """Damage value of a 0x15 packet, the top 3 bits are colour flags."""
    return (p[5] & 0x1F) << 8 | p[6]


def login(account, password):
    """Connect server, then login on the game server. Returns the game server connection and the login result."""
    cs = Conn(CS_PORT, 'cs-' + account)
    p = cs.recv_until(key(0x00, 0x01), what='hello')
    check(bytes(p) == bytes([0xC1, 0x04, 0x00, 0x01]), 'cs hello')
    cs.send([0xC1, 0, 0xF4, 0x02])
    p = cs.recv_until(key(0xF4, 0x02), what='server list')
    check(p[0] == 0xC2 and p[5] == 1 and len(p) == 6 + 4 and p[6] | p[7] << 8 == 0,
          'server list has server 0, 4 bytes per server: ' + p.hex(' '))
    cs.send([0xC1, 0, 0xF4, 0x03, 0x00, 0x00])
    p = cs.recv_until(key(0xF4, 0x03), what='server info')
    ip = bytes(p[4:20]).split(b'\0')[0].decode()
    port = p[20] | p[21] << 8
    check((ip, port) == (HOST, GS_PORT), 'server info {}:{}'.format(ip, port))
    cs.s.close()

    gs = Conn(port, account)
    p = gs.recv_until(key(0xF1, 0x00), what='join result')
    gs.cid = p[5] << 8 | p[6]
    check(p[4] == 1 and bytes(p[7:12]) == b'09704', 'join result cid {} version {}'.format(gs.cid, bytes(p[7:12])))

    tick = struct.pack('<I', int(time.monotonic() * 1000) & 0xFFFFFFFF)
    gs.send([0xC1, 0, 0xF1, 0x01, *name10(account), *name10(password), *tick, *b'09704', *b'muonlineonpython'],
            encrypt=True)
    p = gs.recv_until(key(0xF1, 0x01), what='login result')
    if p[4] == 1:
        gs.joined = True
    return gs, p[4]


def login_ok(account, password):
    gs, result = login(account, password)
    check(result == 1, 'login ' + account)
    return gs


def char_list(gs):
    """Character list entries, 26 bytes each."""
    gs.send([0xC1, 0, 0xF3, 0x00])
    p = gs.recv_until(key(0xF3, 0x00), what='char list')
    check(len(p) == 5 + 26 * p[4], 'char list: {} entries of 26 bytes'.format(p[4]))
    return [p[5 + i * 26:5 + (i + 1) * 26] for i in range(p[4])]


def create(gs, char_name, class_type):
    """class_type as the create screen sends it: class number << 2 (0 dw, 16 dk, 32 elf, 48 mg)"""
    gs.send([0xC1, 0, 0xF3, 0x01, *name10(char_name), class_type])
    return gs.recv_until(key(0xF3, 0x01), what='char created')


def delete(gs, char_name, code):
    gs.send([0xC1, 0, 0xF3, 0x02, *name10(char_name), *name10(code)])
    return gs.recv_until(key(0xF3, 0x02), what='char deleted')[4]


def enter(gs, char_name):
    """Enters the game, returns the character info fields and the skill numbers."""
    gs.send([0xC1, 0, 0xF3, 0x03, *name10(char_name)])
    p = gs.recv_until(key(0xF3, 0x03), what='char info')
    check(p.encrypted and len(p) == 42, 'char info is encrypted, 42 bytes')
    info = dict(zip(INFO_FIELDS, struct.unpack('<4B2I9H2xI2B', bytes(p[4:42]))))
    p = gs.recv_until(key(0xF3, 0x10), what='inventory')
    check(p.encrypted and p[0] == 0xC2 and len(p) == 6 + 5 * p[5], 'inventory is C4, 5 bytes per item')
    info['inventory'] = {p[6 + i * 5]: bytes(p[7 + i * 5:11 + i * 5]) for i in range(p[5])}
    p = gs.recv_until(of(0x12, gs.cid, at=5), what='meet self')
    check(p[4] == 1 and len(p) == 5 + 32 and text(p[23:33]) == char_name, 'meet self, one 32 byte entry, name at entry + 18')
    p = gs.recv_until(key(0xF3, 0x11), what='skill list')
    info['skills'] = [p[5 + i * 3 + 1] for i in range(p[4])]
    check(not any(p.head == 0x0F for p in gs.inbox), 'no weather packet on join')
    print('  {} at {},{} map {}, exp {}/{}, skills {}'.format(
        char_name, info['x'], info['y'], info['map'], info['exp'], info['next_exp'], info['skills']))
    return info


def check_new_character(info, class_type, area):
    s, a, v, e, life, mana = CLASS_STATS[class_type]
    check(in_area(info, area), 'starts at {},{} on map {}, in its start area'.format(info['x'], info['y'], info['map']))
    check((info['exp'], info['next_exp'], info['points']) == (0, 100, 0), 'exp 0 of 100, no level up points')
    check((info['str'], info['agi'], info['vit'], info['ene']) == (s, a, v, e),
          'class base stats str {} agi {} vit {} ene {}'.format(s, a, v, e))
    check((info['life'], info['max_life'], info['mana'], info['max_mana']) == (life, life, mana, mana),
          'full life {} and mana {}'.format(life, mana))
    check((info['money'], info['pk'], info['ctl']) == (0, 3, 0), 'no zen, pk level 3 (commoner), ctl 0')
    check(info['inventory'] == {}, 'empty inventory')


def logout(gs, kind):
    """F1 02 logout request, kind: 0 close, 1 character select, 2 server select. Returns the result packet."""
    gs.send([0xC1, 0, 0xF1, 0x02, kind], encrypt=True)
    p = gs.recv_until(key(0xF1, 0x02), what='logout result')
    gs.inbox.clear()
    return p


def check_server_code():
    """F4 03 carries the server code in 2 bytes: 256 is not server 0"""
    cs = Conn(CS_PORT, 'cs-code')
    cs.recv_until(key(0x00, 0x01), what='hello')
    cs.send([0xC1, 0, 0xF4, 0x03, 0x00, 0x01])
    try:
        p = cs.recv_until(key(0xF4, 0x03), what='closed connection')
        check(False, 'server code 256 answered as ' + p.hex(' '))
    except EOFError:
        check(True, 'server code 256 is unknown, connection closed')


def check_packets():
    """Builders the scripted play doesn't reach, checked against the bytes the client reads."""
    p = SDamage.of(0x1234, 300)
    check(bytes(p) == bytes([0xC1, 7, 0x15, 0x12, 0x34, 0x01, 0x2C]), 'damage 300: ' + p.hex(' '))
    p = SDamage.of(0x1234, 300, SDamage.CRITICAL)
    check(p[5] == 0x81 and damage(p) == 300, 'critical damage 300, blue flag in bit 7 of [5]: ' + p.hex(' '))
    p = SDamage.of(0x1234, 9000, SDamage.EXCELLENT)
    check(p[5] == 0x5F and p[6] == 0xFF, 'damage 9000 shows the 13 bit maximum 8191, green flag: ' + p.hex(' '))


def accounts(t):
    """Login, characters, two players in view."""
    print('packets')
    check_packets()

    print('connect server')
    check_server_code()

    print('player A (dark wizard)')
    a = login_ok('alice', 'pw1')
    check(char_list(a) == [], 'empty char list')
    p = create(a, 'Alice', 0)
    check(p[4] == 1 and text(p[5:15]) == 'Alice' and p[15] == 0, 'char created in slot 0: ' + p.hex(' '))
    e = char_list(a)[0]
    check(e[0] == 0 and text(e[1:11]) == 'Alice' and e[12] | e[13] << 8 == 1 and e[15] == 0
          and bytes(e[16:26]) == NO_EQUIPMENT, 'char list entry ' + e.hex(' '))
    info = enter(a, 'Alice')
    check_new_character(info, 0, LORENCIA)
    check(info['skills'][:1] == [17], 'energy ball is the first skill')
    walk_path(a, (info['x'], info['y']), A_SPOT)
    mob, mob_xy = meet(a, 3)[0]
    check(True, 'meet a spider outside the east exit: cid {} at {}'.format(mob, mob_xy))

    print('wrong password, account in use')
    bad, res = login('alice', 'nope')
    check(res == 0, 'bad password rejected')
    bad.s.close()
    bad, res = login('alice', 'pw1')
    check(res == 3, 'second login of an account in game: in use')
    bad.s.close()

    print('player B (dark knight)')
    b = login_ok('bob', 'pw2')
    p = create(b, 'Bobby', 16)
    check(p[4] == 1 and p[15] == 0, 'char created')
    check(char_list(b)[0][15] == 32, 'char list class byte 32')
    info = enter(b, 'Bobby')
    check_new_character(info, 16, LORENCIA)
    walk_path(b, (info['x'], info['y']), B_SPOT)
    b.recv_until(listed(0x12, a.cid), what='B sees A')
    check(True, 'B sees A')
    p = a.recv_until(listed(0x12, b.cid), what='A sees B')
    check(entry(p, b.cid)[4] == 32, 'A sees B as a dark knight (class byte 32)')
    t.a, t.b, t.mob, t.mob_xy = a, b, mob, mob_xy


def walking(t):
    """Framing, walking in and out of view, walls."""
    a, b, mob = t.a, t.b, t.mob
    print('framing: two packets in one write, then one split in halves')
    x, y = A_SPOT
    a.send_raw(a.build(walk(x, y, [3, 3, 3], 3)) + a.build(walk(x + 3, y, [5], 5)))
    p = b.recv_until(of(0x10, a.cid), what='first move')
    check((p[5], p[6], p[7]) == (x + 3, y, 3 << 4), 'B sees A walk to {},{} facing 3'.format(x + 3, y))
    p = b.recv_until(of(0x10, a.cid), what='second move')
    check((p[5], p[6]) == (x + 3, y + 1), 'B sees A walk to {},{}'.format(x + 3, y + 1))
    half = a.build(walk(x + 3, y + 1, [7], 7))
    a.send_raw(half[:3])
    time.sleep(0.2)
    a.send_raw(half[3:])
    p = b.recv_until(of(0x10, a.cid), what='split move')
    x, y = x + 2, y + 1
    check((p[5], p[6]) == (x, y), 'split packet reassembled')

    print('walk out of view and back')
    a.send(walk(x, y, [3] * 10, 3))  # 10 steps east, still in view
    a.send(walk(x + 10, y, [3] * 10, 3))  # 20 east, 24 tiles from B, at least 17 from the spiders
    b.recv_until(listed(0x14, a.cid), what='B clears A')
    check(True, 'B lost A from view')
    cleared = set()
    while not {b.cid, mob} <= cleared:
        p = a.recv_until(key(0x14), what='A clears B and the monster')
        cleared.update((e[0] << 8 | e[1]) & 0x7FFF for e in entries(p))
    check(True, 'A lost B and the monster from view')
    a.send(walk(x + 20, y, [7] * 10, 7))  # back to 10 east
    p = b.recv_until(listed(0x12, a.cid), what='B meets A again')
    check(tuple(entry(p, a.cid)[2:4]) == (x + 10, y), 'B sees A again at {},{}'.format(x + 10, y))
    a.recv_until(listed(0x12, b.cid), what='A meets B again')
    a.recv_until(listed(0x13, mob), what='A meets mob again')
    check(True, 'A sees B and the monster again')
    a.send(walk(x + 10, y, [7] * 10, 7))
    b.recv_until(lambda p: of(0x10, a.cid)(p) and (p[5], p[6]) == (x, y), what='walk back')
    check(True, 'B sees A walk to {},{}'.format(x, y))
    a_pos = (x, y)

    print('walls stop a walk')
    stop = 0
    while walkable(x, y - stop - 1):
        stop += 1
    check(stop < 8, 'a wall {} tiles north of {},{}'.format(stop + 1, x, y))
    b.inbox.clear()
    a.send(walk(x, y, [1] * 8, 1))
    p = b.recv_until(of(0x10, a.cid), what='walk into the wall')
    check((p[5], p[6]) == (x, y - stop), 'B sees A stop at {},{} in front of the wall'.format(x, y - stop))
    a.send(walk(x, y - stop, [5] * stop, 5))
    b.recv_until(lambda p: of(0x10, a.cid)(p) and (p[5], p[6]) == (x, y), what='walk back from the wall')
    t.a_pos = a_pos


def combat(t):
    """Chat, rotation, magic and melee on the spider."""
    a, b, mob, mob_xy = t.a, t.b, t.mob, t.mob_xy
    print('chat')
    b.send([0xC1, 0, 0x00, *name10('Bobby'), *b'hello there\0'])
    p = a.recv_until(key(0x00), what='chat')
    check(bytes(p[13:]).rstrip(b'\0') == b'hello there', 'A got chat from B')
    b.send(chat('Bobby', '/level 50'))
    p = a.recv_until(key(0x00), what='chat')
    check(text(p[13:]) == '/level 50', 'B is no GM (yet), his command goes out as chat')

    print('rotation')
    a.send([0xC1, 0, 0x18, 0x04, 0x66])
    p = b.recv_until(of(0x18, a.cid), what='rotation')
    check(len(p) == 9 and (p[5], p[6]) == (4, 0x66), 'B sees A rotate: ' + p.hex(' '))

    print('magic: A casts list index 0 at the monster')
    a.send([0xC1, 0, 0x19, 0x00, mob >> 8, mob & 0xFF], encrypt=True)
    p = a.recv_until(key(0x19), what='own skill animation')
    check(p[3] == 17 and (p[4] << 8 | p[5]) == a.cid, 'caster gets energy ball animation with its own id')
    p = b.recv_until(key(0x19), what='skill animation')
    check(p[3] == 17 and (p[4] << 8 | p[5]) == a.cid and p[6] & 0x80 and ((p[6] & 0x7F) << 8 | p[7]) == mob,
          'B sees A cast energy ball on the monster')
    p = b.recv_until(of(0x15, mob), what='magic damage')
    # energy 30: wizardry 30 / 9 .. 30 / 4, energy ball's damage 3 on top, 3 / 2 of it on the max
    ball = damage(p)
    check(6 <= ball <= 11, 'energy ball did {}, wizardry 3..7 with the skill\'s 3: 6..11'.format(ball))
    p = a.recv_until(key(0x27), what='mana')
    check(p[3] == 0xFF and life_value(p) == 59, 'it cost A 1 mana: 27 FF 59')

    print('B kills the monster with melee, A sees the swings')
    b_near = walk_path(b, B_SPOT, near_tile(mob_xy, 1))  # the client walks next to what it attacks
    killed = False
    b.inbox.clear()
    for i in range(40):
        b.send([0xC1, 0, 0x15, mob >> 8, mob & 0xFF, 0x64, 0x06])
        p = b.recv_until(lambda p: p.head in (0x15, 0x16) and (p[3] << 8 | p[4]) & 0x7FFF == mob, what='damage')
        if p.head == 0x16:
            killed = True
            break
        check(3 <= damage(p) <= 7, 'B hits for {}, bare handed a knight does str / 8 .. str / 4'.format(damage(p)))
        time.sleep(ATTACK_PAUSE)
    check(killed, 'monster killed after {} hits'.format(i + 1))
    # a level 2 spider is worth 18..26 exp (usual formula), shared by the damage done: A's ball took some of its life
    t.b_exp = exp16(p)
    check(not p[3] & 0x80 and 0 < t.b_exp <= 26 * (100 - ball) / 100, 'B killed it with a swing (16 cid bit 15 clear): {} exp, '
          'the last hit {}: {}'.format(t.b_exp, p[7] << 8 | p[8], p.hex(' ')))
    b.recv_until(key(0x17), what='kill')
    check(True, 'B got exp and kill packets')
    p = a.recv_until(of(0x18, b.cid), what='attack animation')
    check((p[5], p[6], p[7] << 8 | p[8]) == (6, 0x64, mob), 'A sees B swing at the monster: ' + p.hex(' '))
    p = a.recv_until(lambda p: p.head == 0x16 and (p[3] << 8 | p[4]) & 0x7FFF == mob, what='A\'s share')
    t.a_exp = exp16(p)
    check(p[3] & 0x80 and 0 < t.a_exp <= 26 * ball / 100, 'A gets her share in 16 without a swing (bit 15): {} exp'.format(
        t.a_exp))
    a.recv_until(key(0x17), what='A sees kill')
    check(True, 'A saw the kill')
    p = a.recv_until(listed(0x13, mob), timeout=8, what='respawn')
    check(True, 'monster respawned at {},{}'.format(*entry(p, mob)[6:8]))
    walk_path(b, b_near, B_SPOT)


def items(t):
    """Drops, picking up, wearing, dropping."""
    a, b, mob, mob_xy, a_pos = t.a, t.b, t.mob, t.mob_xy, t.a_pos
    print('the spider drops a sword, a potion and zen for B')
    drops = collect_drops(b, 3, 'B sees the drops')
    check(all(e['dropped'] for e in drops), 'B sees them fall (id bit 15)')
    sword = next(e for e in drops if e.get('item') == SWORD)
    potion = next(e for e in drops if e.get('item') == POTION)
    zen = next(e for e in drops if 'zen' in e)
    check((sword['x'], sword['y']) == mob_xy, 'the sword lies where the spider died, {},{}'.format(*mob_xy))
    check(zen['zen'] == 30, '30 zen, the 24 bit amount around the zen type bytes')
    check(all(max(abs(e['x'] - sword['x']), abs(e['y'] - sword['y'])) <= 2 for e in drops), 'the others next to it')
    seen = collect_drops(a, 3, 'A sees the drops')
    check({e['id'] for e in seen} == {e['id'] for e in drops}, 'A sees the same three')

    print('picking up: the drop is B\'s for a while')
    a_at = walk_path(a, a_pos, (sword['x'], sword['y']))
    p = pick_up(a, sword['id'])
    check(p[3] == 0xFF, 'A may not pick up B\'s sword yet: ' + p.hex(' '))
    b_at = walk_path(b, B_SPOT, (sword['x'], sword['y']))
    p = pick_up(b, sword['id'])
    check(p[3] == 12 and bytes(p[4:8]) == SWORD, 'B picks up the sword into slot 12 (grid 0,0): ' + p.hex(' '))
    item_gone(b, sword['id'], 'sword gone for B')
    item_gone(a, sword['id'], 'sword gone for A')
    check(True, 'A and B get 21 for the sword')
    b_at = walk_path(b, b_at, (potion['x'], potion['y']))
    p = pick_up(b, potion['id'])
    check(p[3] == 13 and bytes(p[4:8]) == POTION, 'the potion goes into slot 13 (grid 1,0): ' + p.hex(' '))
    b_at = walk_path(b, b_at, (zen['x'], zen['y']))
    p = pick_up(b, zen['id'])
    check(p[3] == 0xFE and bytes(p[4:8]) == (30).to_bytes(4, 'big'), 'zen: FE and the money, big endian: ' + p.hex(' '))
    item_gone(a, zen['id'], 'zen gone for A')

    print('moving items: B wears the sword, A sees it')
    p = move_item(b, 13, POTION, 20)
    check(p[3] == 0xFF, 'the potion doesn\'t go on the sword\'s second tile (slot 20)')
    p = move_item(b, 13, POTION, 2)
    check(p[3] == 0xFF, 'a potion is no helm')
    p = move_item(b, 12, SWORD, 0)
    check((p[3], p[4]) == (0, 0) and bytes(p[5:9]) == SWORD, 'B wears the sword in the right hand: ' + p.hex(' '))
    p = a.recv_until(of(0x25, b.cid), what='look change')
    check(len(p) == 9 and (p[5], p[6], p[8]) == (0x01, 0x00, 0x00),
          'A gets 25: type 1, slot 0 << 4 | level 0: ' + p.hex(' '))
    walk_path(a, a_at, a_pos)
    walk_path(b, b_at, B_SPOT)
    b.recv_until(lambda p: of(0x10, a.cid)(p) and (p[5], p[6]) == a_pos, what='A back')

    print('A kills it with energy balls')
    killed = False
    a.inbox.clear()
    for i in range(20):
        a.send([0xC1, 0, 0x19, 0x00, mob >> 8, mob & 0xFF], encrypt=True)
        p = a.recv_until(lambda p: p.head in (0x15, 0x16) and (p[3] << 8 | p[4]) & 0x7FFF == mob, what='magic hit')
        if p.head == 0x16:
            killed = True
            break
        time.sleep(ATTACK_PAUSE)
    check(killed, 'monster killed by magic after {} casts'.format(i + 1))
    t.a_exp += exp16(p)
    check(p[3] & 0x80 and 18 <= exp16(p) <= 26, 'a magic kill: no swing, {} exp for the whole spider'.format(exp16(p)))
    b.recv_until(lambda p: p.head == 0x17 and (p[6] << 8 | p[7]) == a.cid, what='B sees A kill')
    check(True, 'B saw A kill it')
    a.recv_until(listed(0x13, mob), timeout=8, what='respawn 2')

    print('A takes the sword of her kill, can\'t wear it and drops it, B takes it')
    drops = collect_drops(a, 3, 'A sees her drops')
    sword = next(e for e in drops if e.get('item') == SWORD)
    a_at = walk_path(a, a_pos, (sword['x'], sword['y']))
    p = pick_up(a, sword['id'])
    check(p[3] == 12 and bytes(p[4:8]) == SWORD, 'A picks up the sword into slot 12')
    p = move_item(a, 12, SWORD, 0)
    check(p[3] == 0xFF, 'a wizard has too little strength for it (18 of 25)')
    a.send([0xC1, 0, 0x23, *a_at, 12], encrypt=True)
    p = a.recv_until(key(0x23), what='drop result')
    check(len(p) == 5 and (p[3], p[4]) == (1, 12), 'A drops it from slot 12: ' + p.hex(' '))
    # B's inbox still has the drops of A's kill, the sword A took lay on the same tile
    e = None
    while e is None:
        e = next((e for e in collect_drops(b, 1, 'B sees the sword fall')
                  if e.get('item') == SWORD and e['id'] != sword['id']), None)
    check(e['dropped'] and (e['x'], e['y']) == a_at, 'B sees it fall at {},{}'.format(*a_at))
    b_at = walk_path(b, B_SPOT, a_at)
    p = pick_up(b, e['id'])
    check(p[3] == 12 and bytes(p[4:8]) == SWORD, 'B may pick up what a player dropped at once, slot 12 again')
    walk_path(a, a_at, a_pos)
    walk_path(b, b_at, B_SPOT)
    b.recv_until(lambda p: of(0x10, a.cid)(p) and (p[5], p[6]) == a_pos, what='A back')
    b.inbox.clear()


def relog(t):
    """Ping, disconnect, relog, character select and rules, autosave."""
    a, b, a_pos, db_path = t.a, t.b, t.a_pos, t.db_path
    print('ping')
    a.send([0xC1, 0, 0x0E, 0x00, 1, 2, 3, 4, 0x85, 0x00, 0x64, 0x00], encrypt=True)
    a.send([0xC1, 0, 0x18, 0x02, 0x66])
    b.recv_until(of(0x18, a.cid), what='packet after ping')
    check(True, 'connection still fine after ping')

    print('B disconnects')
    b.s.close()
    a.recv_until(listed(0x14, b.cid), what='clear on disconnect')
    check(True, 'A got B cleared after disconnect')

    print('B logs in again, character is still there')
    b2 = login_ok('bob', 'pw2')
    check(b2.cid != b.cid, 'new connection gets a new cid {}'.format(b2.cid))
    e = char_list(b2)
    check([text(x[1:11]) for x in e] == ['Bobby'], 'char list has Bobby')
    look = bytes([0x01]) + NO_EQUIPMENT[1:]
    check(bytes(e[0][16:26]) == look, 'his look in the char list: the sword in the right hand ' + e[0][16:26].hex(' '))
    info = enter(b2, 'Bobby')
    check((info['x'], info['y'], info['exp']) == (*B_SPOT, t.b_exp), 'Bobby is where he left with the exp of his kill')
    bobby_items = {0: SWORD, 12: SWORD, 13: POTION}
    check(info['inventory'] == bobby_items and info['money'] == 30, 'with his items and 30 zen')
    b2.recv_until(listed(0x12, a.cid), what='B sees A after relog')
    p = a.recv_until(listed(0x12, b2.cid), what='A sees B again')
    check(bytes(entry(p, b2.cid)[5:15]) == look, 'A sees B again, with the sword (12 entry + 5)')

    print('A goes back to character select')
    p = logout(a, 1)
    check(p.encrypted and p[4] == 1, 'logout result type 1, encrypted: ' + p.hex(' '))
    b2.recv_until(listed(0x14, a.cid), what='B loses A')
    check(True, 'B lost A from view')
    check([text(e[1:11]) for e in char_list(a)] == ['Alice'], 'char list has Alice')

    print('character rules')
    for name, why in (('Al', 'too short'), ('ALICE', 'name taken, case insensitive'), ('bad name', 'a space'),
                      ('xwebzenx', 'webzen hides it in the client')):
        p = create(a, name, 0)
        check(p[4] == 0, 'refused {!r}: {}'.format(name, why))
    p = create(a, 'Elfie', 32)
    check(p[4] == 1 and p[15] == 1, 'Elfie created in slot 1')
    for slot in range(2, 5):
        p = create(a, 'Extra{}'.format(slot), 48)
        check(p[4] == 1 and p[15] == slot, 'created in slot {}'.format(slot))
    p = create(a, 'Extra5', 16)
    check(p[4] == 2, 'no sixth character: result 2')
    check(len(char_list(a)) == 5, '5 characters')

    print('elves start in Noria')
    info = enter(a, 'Elfie')
    check_new_character(info, 32, NORIA)
    check(logout(a, 1)[4] == 1, 'back to character select')

    print('delete checks the personal code')
    check(delete(a, 'Elfie', 'wrong') == 2, 'wrong code: result 2')
    check(delete(a, 'Bobby', PERSONAL_CODE) == 0, 'another account\'s character: result 0')
    for name in ('Elfie', 'Extra2', 'Extra3', 'Extra4'):
        check(delete(a, name, PERSONAL_CODE) == 1, 'deleted ' + name)
    check([text(e[1:11]) for e in char_list(a)] == ['Alice'], 'only Alice is left')

    print('A enters again, where she logged out')
    info = enter(a, 'Alice')
    check((info['x'], info['y'], info['exp']) == (*a_pos, t.a_exp), 'Alice at {},{} with her exp'.format(*a_pos))
    b2.recv_until(listed(0x12, a.cid), what='B sees A back')
    a.send(walk(*a_pos, [3, 3], 3))
    a_pos = (a_pos[0] + 2, a_pos[1])
    b2.recv_until(lambda p: of(0x10, a.cid)(p) and (p[5], p[6]) == a_pos, what='A walks')
    time.sleep(2.5)
    with sqlite3.connect(db_path) as db:
        row = db.execute('SELECT x, y FROM characters WHERE name = ?', ('Alice',)).fetchone()
    check(row == a_pos, 'autosave wrote the position {},{}'.format(*row))
    a.send(walk(*a_pos, [3], 3))
    a_pos = (a_pos[0] + 1, a_pos[1])
    b2.recv_until(lambda p: of(0x10, a.cid)(p) and (p[5], p[6]) == a_pos, what='A walks')
    t.a, t.b2, t.a_pos, t.bobby_items = a, b2, a_pos, bobby_items


def restart(t):
    """The game server restarts, characters keep what they had."""
    a, b2, a_pos, bobby_items, servers, db_path = t.a, t.b2, t.a_pos, t.bobby_items, t.servers, t.db_path
    print('restart the game server')
    servers['bin/gs.py'].stop()
    check(servers['bin/gs.py'].proc.returncode == 0, 'game server shut down cleanly')
    a.s.close()
    b2.s.close()
    with sqlite3.connect(db_path) as db:
        row = db.execute('SELECT x, y FROM characters WHERE name = ?', ('Alice',)).fetchone()
        check(row == a_pos, 'shutdown saved Alice at {},{}'.format(*row))
        password_hash = db.execute('SELECT password_hash FROM accounts WHERE name = ?', ('alice',)).fetchone()[0]
        check(password_hash.startswith('scrypt$') and 'pw1' not in password_hash, 'password stored hashed')
        db.execute('UPDATE characters SET zen = 31337 WHERE name = ?', ('Alice',))
        db.execute("UPDATE accounts SET ctl_code = 32 WHERE name IN ('alice', 'bob')")  # GM, bin/account.py gm
    servers['bin/gs.py'].start()

    a = login_ok('alice', 'pw1')
    e = char_list(a)
    check(len(e) == 1 and text(e[0][1:11]) == 'Alice', 'Alice is in the char list after the restart')
    info = enter(a, 'Alice')
    check((info['x'], info['y'], info['map'], info['exp']) == (*a_pos, 0, t.a_exp),
          'Alice is back at {},{} with her exp'.format(*a_pos))
    check((info['money'], info['pk'], info['ctl']) == (31337, 3, 0), 'money 31337 at 36, pk level 3 at 40, ctl at 41')
    bad, res = login('alice', 'nope')
    check(res == 0, 'bad password still rejected')
    bad.s.close()
    b3 = login_ok('bob', 'pw2')
    info = enter(b3, 'Bobby')
    check((info['x'], info['y'], info['exp']) == (*B_SPOT, t.b_exp), 'Bobby too')
    check(info['inventory'] == bobby_items and info['money'] == 30, 'his items and zen too')
    a.recv_until(listed(0x12, b3.cid), what='A sees B after the restart')
    check(True, 'A sees B after the restart')
    max_life, max_mana = info['max_life'], info['max_mana']

    print('GM commands')
    a.send(chat('Alice', '/level 10'))
    p = a.recv_until(key(0xF3, 0x05), what='level up')
    check(struct.unpack('<2H', bytes(p[4:8])) == (10, 45), 'A, a GM, goes to level 10 with /level: F3 05 level 10 '
          'and the 45 points of 9 levels: ' + p.hex(' '))
    p = a.recv_until(key(0xF3, 0x04), what='refresh')
    t.a_exp = struct.unpack('<I', bytes(p[12:16]))[0]
    check(t.a_exp == 14580, 'F3 04 brings her exp to level 10\'s, 10 (L + 9) L² of level 9: {}'.format(t.a_exp))
    p = a.recv_until(key(0x0D), what='notice')
    check(text(p[4:]) == 'level 10', 'the answer is a notice: ' + text(p[4:]))
    a.send(chat('Alice', '/fly'))
    p = a.recv_until(key(0x0D), what='notice')
    check(text(p[4:]).startswith('unknown command'), 'an unknown command: ' + text(p[4:]))
    a.send(chat('Alice', 'level 50'))
    p = b3.recv_until(lambda p: p.head == 0x00 and text(p[3:13]) == 'Alice', what='A\'s line')
    check(text(p[13:]) == 'level 50', 'a line without / goes out as chat')

    print('level up points')
    a.send([0xC1, 0, 0xF3, 0x06, 2])
    p = a.recv_until(key(0xF3, 0x06), what='point result')
    # a dark wizard: 60 life at level 1, + 1 per level, + 2 per vitality point
    check(len(p) == 8 and p[4] == 0x12 and struct.unpack('<H', bytes(p[6:8]))[0] == 60 + 9 + 2,
          'A puts a point into vitality: 12, the new max life {} at 6: {}'.format(60 + 9 + 2, p.hex(' ')))
    a.send([0xC1, 0, 0xF3, 0x06, 0])
    p = a.recv_until(key(0xF3, 0x06), what='point result')
    check(p[4] == 0x10, 'and one into strength: 10')
    b3.send([0xC1, 0, 0xF3, 0x06, 1])
    p = b3.recv_until(key(0xF3, 0x06), what='point result')
    check(p[4] >> 4 == 0, 'B has no points: refused, high nibble 0')
    t.a, t.b3, t.max_life, t.max_mana = a, b3, max_life, max_mana


def skills(t):
    """Learning from a scroll, area skills hit what the client reports, poison runs out, teleport, a weapon skill."""
    a, b3, a_pos = t.a, t.b3, t.a_pos

    print('learning: A reads a scroll')
    for _ in range(10):
        a.send([0xC1, 0, 0xF3, 0x06, 3])
        check(a.recv_until(key(0xF3, 0x06), what='energy')[4] == 0x13, 'a point into energy')
    # the fire ball scroll: drop level 5, energy base 10, needs 5 * 10 * 4 / 10 + 20 = 40 energy, A has 30 + 10
    a.send(chat('Alice', '/item 15 3'))
    slot = next(s for s, i in inventory(a).items() if i[0] == 0xE3 and i[3] & 0x80)
    a.send([0xC1, 0, 0x26, slot, 0], encrypt=True)
    check(skill_change(a) == (0xFE, 1, 4), 'A reads it (26): F3 11 FE puts fire ball (4) in list slot 1')
    p = a.recv_until(key(0x28), what='scroll used')
    check((p[3], p[4]) == (slot, 1), 'the scroll is gone: 28 deletes slot {}, unlocks item use'.format(slot))
    a.send(chat('Alice', '/item 15 0'))
    slot = next(s for s, i in inventory(a).items() if i[0] == 0xE0 and i[3] & 0x80)
    a.send([0xC1, 0, 0x26, slot, 0], encrypt=True)
    p = a.recv_until(key(0x26), what='refused')
    check(p[3] == 0xFD, 'the poison scroll needs 140 energy: refused, 26 FD unlocks item use')
    a.send(chat('Alice', '/skill 5'))
    check(skill_change(a) == (0xFE, 2, 5), 'flame (5) by GM command into slot 2')
    a.send(chat('Alice', '/skill 1'))
    check(skill_change(a) == (0xFE, 3, 1), 'poison (1) into slot 3')
    a.send(chat('Alice', '/skill 6'))
    check(skill_change(a) == (0xFE, 4, 6), 'teleport (6) into slot 4')

    print('area skill: flame hits what the client reports landing near it')
    spot = (GOBLIN_SPOT[0], GOBLIN_SPOT[1] - 4)
    a.inbox.clear()
    a.send(chat('Alice', '/move 0 {} {}'.format(*spot)))
    p = a.recv_until(key(0x1C), what='GM move')
    check((p[3], p[4], p[5], p[6]) == (1, 0, *spot), 'A moves to {},{} (1C)'.format(*spot))
    (g1, g1_xy), (g2, g2_xy) = meet(a, 26, 2)
    check(True, 'A sees the goblins at {},{} and {},{}'.format(*g1_xy, *g2_xy))
    a.send([0xC1, 0, 0x1E, 2, *g1_xy, 0], encrypt=True)
    p = a.recv_until(key(0x1E), what='area skill animation')
    check(p[3] == 5 and (p[4] << 8 | p[5]) == a.cid and (p[6], p[7]) == g1_xy, 'A casts flame at the first goblin')
    p = a.recv_until(key(0x27), what='mana')
    mana = life_value(p)
    check(True, 'it costs 50 mana, {} left'.format(mana))
    a.send([0xC1, 0, 0x1D, 2, *g1_xy, 1, 2, g1 >> 8, g1 & 0xFF, g2 >> 8, g2 & 0xFF], encrypt=True)
    hit = {g1: damage(a.recv_until(of(0x15, g1), what='flame on goblin 1')),
           g2: damage(a.recv_until(of(0x15, g2), what='flame on goblin 2'))}
    # energy 40: wizardry 4..10, flame's 25 on top, 3 / 2 of it on the max
    check(all(29 <= d <= 47 for d in hit.values()), 'the 1D report hits both goblins: {} (29..47)'.format(
        list(hit.values())))
    a.send([0xC1, 0, 0x1D, 2, *g1_xy, 1, 1, g1 >> 8, g1 & 0xFF], encrypt=True)
    a.send([0xC1, 0, 0x1D, 2, g1_xy[0], g1_xy[1] - 12, 3, 1, g2 >> 8, g2 & 0xFF], encrypt=True)
    a.send([0xC1, 0, 0x1D, 1, *g1_xy, 4, 1, g2 >> 8, g2 & 0xFF], encrypt=True)
    chat_round_trip(a, 'Alice')
    check(not any(of(0x15, g1)(p) or of(0x15, g2)(p) for p in a.inbox),
          'nothing for the same effect again, a landing 12 tiles off or a skill not cast')
    a.send([0xC1, 0, 0x1D, 2, *g1_xy, 2, 1, g2 >> 8, g2 & 0xFF], encrypt=True)
    p = a.recv_until(of(0x15, g2), what='second effect')
    check(True, 'another effect of the cast (serial 2) hits goblin 2 again: {}'.format(damage(p)))

    print('poison hurts for a while and ends with 1B')
    a.send(chat('Alice', '/heal'))
    check(notice(a, 'healed'), 'A gets her mana back with /heal')
    a.send([0xC1, 0, 0x19, 3, g1 >> 8, g1 & 0xFF], encrypt=True)
    p = a.recv_until(lambda p: p.head == 0x19 and p[3] == 1, what='poison animation')
    check(p[3] == 1 and p[6] & 0x80 and ((p[6] & 0x7F) << 8 | p[7]) == g1, 'poison takes effect (19 bit 15)')
    a.recv_until(of(0x15, g1), what='poison hit')
    p = a.recv_until(of(0x15, g1), timeout=4, what='poison damage')
    check(True, 'the poison hurts on its own: {}'.format(damage(p)))
    p = a.recv_until(of(0x1B, g1, at=4), timeout=12, what='poison ends')
    check(len(p) == 6 and p[3] == 1, '1B: poison (1) of the goblin ended: ' + p.hex(' '))

    print('teleport')
    target = (spot[0] - 4, spot[1] - 3)
    a.send([0xC1, 0, 0x1C, 0, *target], encrypt=True)
    p = a.recv_until(key(0x1C), what='teleport')
    check(p.encrypted and (p[3], p[4], p[5], p[6]) == (0, 0, *target), 'A teleports to {},{}: 1C 0 '.format(*target)
          + p.hex(' '))
    p = b3.recv_until(of(0x11, a.cid), what='B sees the teleport')
    check((p[5], p[6]) == target, 'B sees A appear there (11)')
    a.send([0xC1, 0, 0x1C, 0, *spot], encrypt=True)
    chat_round_trip(a, 'Alice')
    check(not any(p.head == 0x1C for p in a.inbox), 'not again within 3 s')
    a.send(chat('Alice', '/move 0 {} {}'.format(*a_pos)))
    a.recv_until(key(0x1C), what='GM move back')

    print('weapon skills: B wears a shield with the defense skill')
    b3.send(chat('Bobby', '/level 5'))
    p = b3.recv_until(key(0xF3, 0x05), what='level 5')
    t.max_life = struct.unpack('<H', bytes(p[8:10]))[0]
    t.b_exp = struct.unpack('<I', bytes(b3.recv_until(key(0xF3, 0x04), what='refresh')[12:16]))[0]
    # the buckler needs 34 strength, the skill 30 mana (a knight's stamina): 6 points into strength, 10 into energy
    for stat in [0] * 6 + [3] * 10:
        b3.send([0xC1, 0, 0xF3, 0x06, stat])
        p = b3.recv_until(key(0xF3, 0x06), what='point')
    t.max_mana = struct.unpack('<H', bytes(p[6:8]))[0]
    b3.send(chat('Bobby', '/heal'))
    notice(b3, 'healed')
    b3.send(chat('Bobby', '/item 6 4 0 1'))  # buckler with its skill, 34 strength
    slot, buckler = next((s, i) for s, i in inventory(b3).items() if i[0] == 0xC4)
    p = move_item(b3, slot, buckler, 1)
    check((p[3], p[4]) == (0, 1), 'B wears the buckler in the left hand')
    check(skill_change(b3) == (0xFE, 0, 18), 'F3 11 FE gives him its defense skill (18) in slot 0')
    b3.send([0xC1, 0, 0x19, 0, b3.cid >> 8, b3.cid & 0xFF], encrypt=True)
    p = b3.recv_until(lambda p: p.head == 0x19 and p[3] == 18, what='defense')
    check(of(0x19, b3.cid, at=4)(p) and p[6] & 0x80, 'he uses it on himself, it takes effect: ' + p.hex(' '))
    p = move_item(b3, 1, buckler, slot)
    check((p[3], p[4]) == (0, slot), 'B puts the buckler away')
    check(skill_change(b3)[:2] == (0xFF, 0), 'and loses the skill: F3 11 FF slot 0')

    print('A\'s skills and hotkeys after relog')
    hotkeys = [17, 4, 0, 0, 0, 0, 0, 0, 0, 5]
    a.send([0xC1, 0, 0xF3, 0x30, *hotkeys, 0x09, 0x00, 0x04, 0x08])  # the client sends them before logging out
    check(logout(a, 1)[4] == 1, 'A goes to character select')
    info = enter(a, 'Alice')
    check(info['skills'] == [17, 4, 5, 1, 6], 'her skills in their slots: {}'.format(info['skills']))
    p = a.recv_until(key(0xF3, 0x30), what='key settings')
    check(len(p) == 18 and list(p[4:14]) == [17, 4] + [0xFF] * 7 + [5] and bytes(p[14:18]) == b'\x09\x00\x04\x08',
          'F3 30 after the skill list: her hotkeys by skill number, FF for none: ' + p.hex(' '))
    b3.recv_until(listed(0x12, a.cid), what='B sees A back')

    print('an elf: greater damage on B, arrows, a miss')
    check(logout(a, 1)[4] == 1, 'A goes to character select')
    check(create(a, 'Elfa', 32)[4] == 1, 'A creates an elf')
    enter(a, 'Elfa')
    a.send(chat('Elfa', '/level 10'))  # greater damage takes 40 mana, a new elf has 30
    a.recv_until(key(0xF3, 0x05), what='level 10')
    a.send(chat('Elfa', '/move 0 {} {}'.format(B_SPOT[0] + 2, B_SPOT[1])))
    a.recv_until(key(0x1C), what='GM move')
    a.send(chat('Elfa', '/skill 28'))
    check(skill_change(a) == (0xFE, 0, 28), 'greater damage (28) into slot 0')
    a.send([0xC1, 0, 0x19, 0, b3.cid >> 8, b3.cid & 0xFF], encrypt=True)
    p = b3.recv_until(lambda p: p.head == 0x19 and p[3] == 28, what='buff')
    check(of(0x19, a.cid, at=4)(p) and p[6] & 0x80 and ((p[6] & 0x7F) << 8 | p[7]) == b3.cid,
          'B sees the elf\'s greater damage take effect on him (19 bit 15)')
    a.send(chat('Elfa', '/skill 30'))
    check(skill_change(a) == (0xFE, 1, 30), 'goblin summon (30) into slot 1')
    a.send(chat('Elfa', '/heal'))
    notice(a, 'healed')
    a.send([0xC1, 0, 0x19, 1, a.cid >> 8, a.cid & 0xFF], encrypt=True)  # the client sends a summon at the hero
    for conn in (a, b3):
        p = conn.recv_until(key(0x1F), what='summon in view')
        e = entries(p)[0]
        check(len(p) == 5 + 22 * p[4] and e[2] == 26 and text(e[11:21]) == 'Elfa',
              '{} sees the goblin in 1F, 22 byte entries, the owner\'s name at + 11'.format(conn.name))
    goblin = (e[0] << 8 | e[1]) & 0x7FFF
    a.send(chat('Elfa', '/item 4 0'))
    bow_slot, bow = next((s, i) for s, i in inventory(a).items() if i[0] == 0x80)
    a.send(chat('Elfa', '/item 4 15'))
    arrows_slot, arrows = next((s, i) for s, i in inventory(a).items() if i[0] == 0x8F)
    check(arrows[2] == 255, 'a stack of 255 arrows')
    check(move_item(a, bow_slot, bow, 1)[4] == 1 and move_item(a, arrows_slot, arrows, 0)[4] == 0,
          'the bow in the left hand, the arrows in the right')
    a.send(chat('Elfa', '/move 0 {} {}'.format(*spot)))
    a.recv_until(key(0x1C), what='GM move')
    (dodger, _), = meet(a, 7)
    misses = 0
    for i in range(5):
        time.sleep(ATTACK_PAUSE)
        a.send([0xC1, 0, 0x15, dodger >> 8, dodger & 0xFF, 0x64, 0x00])
        p = a.recv_until(key(0x2A), what='arrow shot')
        check(len(p) == 6 and (p[3], p[4]) == (0, 254 - i), 'a shot takes an arrow: 2A slot 0, {} left'.format(254 - i))
        misses += damage(a.recv_until(of(0x15, dodger), what='shot')) == 0
    check(misses > 0, 'the dodger, defense rate 100000, takes 5% of the hits: {} of 5 missed (15 with 0)'.format(misses))
    p = a.recv_until(lambda p: of(0x18, goblin)(p) and (p[7] << 8 | p[8]) == dodger, timeout=8, what='summon attacks')
    check(True, 'the goblin came after the elf and attacks the dodger with her')
    check(logout(a, 1)[4] == 1, 'the elf goes to character select')
    info = enter(a, 'Alice')
    check((info['x'], info['y']) == a_pos, 'and Alice is back at {},{}'.format(*a_pos))


def monsters(t):
    """Monsters chase, hit and kill, potions, regeneration, respawn."""
    b3, max_life, max_mana = t.b3, t.max_life, t.max_mana
    b3.inbox.clear()
    print('a monster chases and hits')
    look = walk_path(b3, B_SPOT, near_tile(DRAGON_SPOT, 10))
    p = b3.recv_until(lambda p: p.head == 0x13 and any(e[2] == 2 for e in entries(p)), what='B meets the dragon')
    e = next(e for e in entries(p) if e[2] == 2)
    dragon, dragon_xy = (e[0] << 8 | e[1]) & 0x7FFF, (e[6], e[7])
    check(True, 'B sees the dragon at {},{}'.format(*dragon_xy))
    spot = walk_path(b3, look, near_tile(dragon_xy, 4))
    b3.recv_until(of(0x10, dragon), what='dragon walks to B')
    check(True, 'the dragon comes for B at {},{}'.format(*spot))
    p = b3.recv_until(of(0x18, dragon), timeout=5, what='dragon attacks')
    check(p[6] == 0x64, 'B sees the dragon attack, animation 0x64: ' + p.hex(' '))
    p = b3.recv_until(of(0x15, b3.cid), what='damage to B')
    check(damage(p) == 1, 'B takes 1 damage')
    p = b3.recv_until(key(0x26), what='life')
    check(len(p) == 6 and p[3] == 0xFF and life_value(p) == max_life - 1, 'life 26 FF, value big endian: ' + p.hex(' '))

    print('B drinks the potion')
    p = b3.recv_until(lambda p: p.head == 0x26 and p[3] == 0xFF and life_value(p) <= max_life - 3, what='3 hits')
    before = life_value(p)
    b3.send([0xC1, 0, 0x26, 13, 0], encrypt=True)
    # regeneration adds 1 of 110 every 3 s, the dragon takes 1 every 0.5 s: only the potion brings back all life
    p = b3.recv_until(lambda p: p.head == 0x26 and p[3] == 0xFF and life_value(p) == max_life, what='potion')
    check(True, 'the potion heals B from {} to {}'.format(before, max_life))
    p = b3.recv_until(key(0x28), what='potion used up')
    check(len(p) == 5 and (p[3], p[4]) == (13, 1), 'it was the last one: 28 deletes slot 13, unlocks item use')
    b3.inbox.clear()  # hits from before the potion
    p = b3.recv_until(lambda p: p.head == 0x26 and p[3] == 0xFF and life_value(p) < max_life, what='hit again')

    print('B gets away, life regenerates')
    walk_path(b3, spot, B_SPOT)
    drain(b3, 0.5)
    # B is 1 below full life, the regeneration may have come while walking
    life, regen = life_value(p), None
    for q in b3.inbox:
        if q.head == 0x26 and q[3] == 0xFF:
            if regen is None and life_value(q) > life:
                regen = life, life_value(q)
            life = life_value(q)
    b3.inbox.clear()
    if regen is None:
        p = b3.recv_until(lambda p: p.head == 0x26 and life_value(p) > life, timeout=5, what='regeneration')
        regen = life, life_value(p)
    check(True, 'life regenerates from {} to {}'.format(*regen))
    check(not any(p.head == 0x15 for p in b3.inbox), 'no more hits')

    print('a monster kills B, B comes back in town')
    look = walk_path(b3, B_SPOT, near_tile(HOUND_SPOT, 10))
    p = b3.recv_until(lambda p: p.head == 0x13 and any(e[2] == 5 for e in entries(p)), what='B meets the hound')
    e = next(e for e in entries(p) if e[2] == 5)
    walk_path(b3, look, near_tile((e[6], e[7]), 3))
    b3.recv_until(of(0x17, b3.cid), timeout=5, what='B killed')
    check(True, 'B is killed')
    p = b3.recv_until(key(0xF3, 0x04), timeout=6, what='respawn')
    x, y, map_id, _, life, mana, exp, money = struct.unpack('<4B2H2I', bytes(p[4:20]))
    check(len(p) == 20 and in_area({'map': map_id, 'x': x, 'y': y}, LORENCIA),
          'B respawns at {},{} in Lorencia: {}'.format(x, y, p.hex(' ')))
    check((life, mana, exp, money) == (max_life, max_mana, t.b_exp, 30), 'full life and mana, level 5 keeps its exp')
    t.b_at = (x, y)  # where B respawned


def gates(t):
    """Gates: Lorencia to Noria."""
    a, b3, a_pos, (x, y) = t.a, t.b3, t.a_pos, t.b_at
    print('gates: Lorencia to Noria through gate 23, from level 10')
    gate, xs, ys = NORIA_GATE
    walk_path(b3, (x, y), (xs[0], ys[0]))
    b3.send([0xC1, 0, 0x1C, gate, 0, 0], encrypt=True)
    chat_round_trip(b3, 'Bobby')
    check(not any(p.head == 0x1C for p in b3.inbox), 'level 5 B stays in Lorencia')
    a.send([0xC1, 0, 0x1C, gate, 0, 0], encrypt=True)
    chat_round_trip(a, 'Alice')
    check(not any(p.head == 0x1C for p in a.inbox), 'A away from the gate stays')
    walk_path(a, a_pos, (xs[1], ys[0]))
    b3.recv_until(listed(0x12, a.cid), what='B sees A at the gate')
    a.send([0xC1, 0, 0x1C, gate, 0, 0], encrypt=True)
    p = a.recv_until(key(0x1C), what='map change')
    map_id, xs, ys, direction = NORIA_ARRIVAL
    check(p.encrypted and len(p) == 8 and p[3] == 1 and p[4] == map_id and p[5] in xs and p[6] in ys
          and p[7] == direction, 'A moves to Noria at {},{}: {}'.format(p[5], p[6], p.hex(' ')))
    a.send([0xC1, 0, 0xF3, 0x12])
    b3.recv_until(listed(0x14, a.cid), what='B loses A')
    check(True, 'B lost A from view')
    chat_round_trip(a, 'Alice')


def play(servers, db_path):
    """The test, area by area. t carries the clients and what one area leaves for the next."""
    t = SimpleNamespace(servers=servers, db_path=db_path)
    accounts(t)
    walking(t)
    combat(t)
    items(t)
    relog(t)
    restart(t)
    skills(t)
    monsters(t)
    gates(t)

def port_open(port):
    try:
        socket.create_connection((HOST, port), timeout=0.2).close()
        return True
    except OSError:
        return False


class Server:
    """A server script run with the test config, its log kept across restarts."""

    def __init__(self, script, port, config):
        self.script = script
        self.port = port
        self.config = config
        self.log = tempfile.NamedTemporaryFile('w+', prefix=Path(script).stem + '-', suffix='.log', delete=False)
        self.proc = None

    def start(self):
        self.proc = subprocess.Popen([sys.executable, '-u', self.script], cwd=ROOT, stdout=self.log,
                                     stderr=subprocess.STDOUT, env={**os.environ, 'MU_CONFIG': self.config})
        deadline = time.time() + 10
        while not port_open(self.port):
            if time.time() > deadline or self.proc.poll() is not None:
                raise AssertionError(self.script + ' did not start')
            time.sleep(0.1)

    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(5)


def main():
    if port_open(CS_PORT) or port_open(GS_PORT):
        print('ports {} / {} are in use, stop the running servers first'.format(CS_PORT, GS_PORT))
        return 2

    tmp = tempfile.TemporaryDirectory(prefix='mu-test-')
    db_path = os.path.join(tmp.name, 'mu.db')
    config = os.path.join(tmp.name, 'config.ini')
    monsters = os.path.join(tmp.name, 'Monster.txt')
    spawns = os.path.join(tmp.name, 'MonsterSetBase.txt')
    drops = os.path.join(tmp.name, 'ItemDrop.txt')
    Path(monsters).write_text(MONSTERS)
    Path(spawns).write_text(SPAWNS)
    Path(drops).write_text(DROPS)
    Path(config).write_text(CONFIG.format(cs_port=CS_PORT, gs_port=GS_PORT, host=HOST, db=db_path, monsters=monsters,
                                          spawns=spawns, drops=drops, code=PERSONAL_CODE))
    servers = {script: Server(script, port, config) for script, port in (('bin/cs.py', CS_PORT), ('bin/gs.py', GS_PORT))}
    try:
        for s in servers.values():
            s.start()
        play(servers, db_path)
        print('ALL OK')
        return 0
    except (AssertionError, EOFError, OSError) as e:
        print('FAILED:', e)
        for s in servers.values():
            s.log.flush()
            print('--- {} ({})'.format(s.script, s.log.name))
            print(''.join(Path(s.log.name).read_text(errors='replace').splitlines(True)[-30:]))
        return 1
    finally:
        for s in servers.values():
            s.stop()
        tmp.cleanup()


if __name__ == '__main__':
    sys.exit(main())
