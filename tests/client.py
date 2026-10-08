"""
Scripted 0.97 client: starts the connect and game server, then plays them over real sockets the way the
client does (same keys, encryption, xor and packet layouts, see docs/protocol-097.md) and checks the answers.

usage: ./venv/bin/python tests/client.py
Exits non zero on the first failed check and prints the end of the server logs.
The servers run with their own config on ports 44415 and 55911 and a database in a temporary directory, so the test
can run next to the usual servers.
"""
import os
import socket
import sqlite3
import struct
import subprocess
import sys
import tempfile
import time
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
cs_port = {}
gs_port = {}
gs_host = {}
[database]
db_path = {{}}
autosave_interval = 2
[accounts]
personal_code = {}
[log]
log_level = DEBUG
log_packets = yes
""".format(CS_PORT, GS_PORT, HOST, PERSONAL_CODE)

# x, y step of each walk direction
STEPS = [(-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0)]
# start areas: Lorencia gate 17, Noria gate 27 for elves (Move/Gate.txt)
LORENCIA = (0, range(133, 152), range(118, 136))
NORIA = (3, range(171, 178), range(108, 118))
# where A and B stand for the tests in view: outside the east exit of Lorencia, next to the spiders the server puts
# there (x 177..185, y 124..128). The walks from here stay on walkable tiles outside the safe zone
A_SPOT = (180, 127)
B_SPOT = (178, 126)
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


def walk_to(conn, start, target):
    """Walks straight (diagonals first) from start to target, at most 15 steps per request."""
    (x, y), steps = start, []
    while (x, y) != target:
        dx, dy = (target[0] > x) - (target[0] < x), (target[1] > y) - (target[1] < y)
        steps.append(STEPS.index((dx, dy)))
        x, y = x + dx, y + dy
    x, y = start
    for i in range(0, len(steps), 15):
        part = steps[i:i + 15]
        conn.send(walk(x, y, part, part[-1]))
        for d in part:
            x, y = x + STEPS[d][0], y + STEPS[d][1]
    return target


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
    gs.recv_until(key(0xF3, 0x10), what='inventory')
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


def play(servers, db_path):
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
          and bytes(e[16:26]) == bytes([0xFF] * 5 + [0, 0, 0, 0xF8, 0]), 'char list entry ' + e.hex(' '))
    info = enter(a, 'Alice')
    check_new_character(info, 0, LORENCIA)
    check(info['skills'][:1] == [17], 'energy ball is the first skill')
    walk_to(a, (info['x'], info['y']), A_SPOT)
    p = a.recv_until(key(0x13), what='meet monster')
    mob = p[5] << 8 | p[6]
    mob_xy = (p[11], p[12])
    check(p[7] == 3, 'meet a spider outside the east exit: cid {} type {} at {}'.format(mob, p[7], mob_xy))

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
    walk_to(b, (info['x'], info['y']), B_SPOT)
    b.recv_until(of(0x12, a.cid, at=5), what='B sees A')
    check(True, 'B sees A')
    p = a.recv_until(of(0x12, b.cid, at=5), what='A sees B')
    check(p[9] == 32, 'A sees B as a dark knight (class byte 32)')

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
    b.recv_until(of(0x14, a.cid, at=4), what='B clears A')
    check(True, 'B lost A from view')
    a.recv_until(of(0x14, b.cid, at=4), what='A clears B')
    a.recv_until(of(0x14, mob, at=4), what='A clears mob')
    check(True, 'A lost B and the monster from view')
    a.send(walk(x + 20, y, [7] * 10, 7))  # back to 10 east
    p = b.recv_until(of(0x12, a.cid, at=5), what='B meets A again')
    check((p[7], p[8]) == (x + 10, y), 'B sees A again at {},{}'.format(x + 10, y))
    a.recv_until(of(0x12, b.cid, at=5), what='A meets B again')
    a.recv_until(of(0x13, mob, at=5), what='A meets mob again')
    check(True, 'A sees B and the monster again')
    a.send(walk(x + 10, y, [7] * 10, 7))
    b.recv_until(lambda p: of(0x10, a.cid)(p) and (p[5], p[6]) == (x, y), what='walk back')
    check(True, 'B sees A walk to {},{}'.format(x, y))
    a_pos = (x, y)

    print('chat')
    b.send([0xC1, 0, 0x00, *name10('Bobby'), *b'hello there\0'])
    p = a.recv_until(key(0x00), what='chat')
    check(bytes(p[13:]).rstrip(b'\0') == b'hello there', 'A got chat from B')

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
    check(damage(p) == 15, 'magic did 15 damage')

    print('area magic: A casts flame (list index 5) on the monster')
    a.send([0xC1, 0, 0x1E, 5, mob_xy[0], mob_xy[1], 0], encrypt=True)
    p = b.recv_until(key(0x1E), what='area skill animation')
    check(p[3] == 5 and (p[4] << 8 | p[5]) == a.cid and (p[6], p[7]) == mob_xy, 'B sees A cast flame at the monster')
    p = b.recv_until(of(0x15, mob), what='area magic damage')
    check(damage(p) == 20, 'area magic did 20 damage')

    print('B kills the monster with melee, A sees the swings')
    killed = False
    b.inbox.clear()
    for i in range(40):
        b.send([0xC1, 0, 0x15, mob >> 8, mob & 0xFF, 0x64, 0x06])
        p = b.recv_until(lambda p: p.head in (0x15, 0x16) and (p[3] << 8 | p[4]) == mob, what='damage')
        if p.head == 0x16:
            killed = True
            break
        time.sleep(0.05)
    check(killed, 'monster killed after {} hits'.format(i + 1))
    b.recv_until(key(0x17), what='kill')
    check(True, 'B got exp and kill packets')
    p = a.recv_until(of(0x18, b.cid), what='attack animation')
    check((p[5], p[6], p[7] << 8 | p[8]) == (6, 0x64, mob), 'A sees B swing at the monster: ' + p.hex(' '))
    a.recv_until(key(0x17), what='A sees kill')
    check(True, 'A saw the kill')
    p = a.recv_until(of(0x13, mob, at=5), timeout=8, what='respawn')
    check(True, 'monster respawned at {},{}'.format(p[11], p[12]))

    print('A kills it with energy balls')
    killed = False
    a.inbox.clear()
    for i in range(20):
        a.send([0xC1, 0, 0x19, 0x00, mob >> 8, mob & 0xFF], encrypt=True)
        p = a.recv_until(lambda p: p.head in (0x15, 0x16) and (p[3] << 8 | p[4]) == mob, what='magic hit')
        if p.head == 0x16:
            killed = True
            break
        time.sleep(0.05)
    check(killed, 'monster killed by magic after {} casts'.format(i + 1))
    b.recv_until(lambda p: p.head == 0x17 and (p[6] << 8 | p[7]) == a.cid, what='B sees A kill')
    check(True, 'B saw A kill it')
    a.recv_until(of(0x13, mob, at=5), timeout=8, what='respawn 2')
    b.inbox.clear()

    print('ping')
    a.send([0xC1, 0, 0x0E, 0x00, 1, 2, 3, 4, 0x85, 0x00, 0x64, 0x00], encrypt=True)
    a.send([0xC1, 0, 0x18, 0x02, 0x66])
    b.recv_until(of(0x18, a.cid), what='packet after ping')
    check(True, 'connection still fine after ping')

    print('B disconnects')
    b.s.close()
    a.recv_until(of(0x14, b.cid, at=4), what='clear on disconnect')
    check(True, 'A got B cleared after disconnect')

    print('B logs in again, character is still there')
    b2 = login_ok('bob', 'pw2')
    check(b2.cid != b.cid, 'new connection gets a new cid {}'.format(b2.cid))
    check([text(e[1:11]) for e in char_list(b2)] == ['Bobby'], 'char list has Bobby')
    info = enter(b2, 'Bobby')
    check((info['x'], info['y'], info['exp']) == (*B_SPOT, 90), 'Bobby is where he left with the exp of his kill')
    b2.recv_until(of(0x12, a.cid, at=5), what='B sees A after relog')
    a.recv_until(of(0x12, b2.cid, at=5), what='A sees B again')
    check(True, 'A and B see each other again')

    print('A goes back to character select')
    p = logout(a, 1)
    check(p.encrypted and p[4] == 1, 'logout result type 1, encrypted: ' + p.hex(' '))
    b2.recv_until(of(0x14, a.cid, at=4), what='B loses A')
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
    check((info['x'], info['y'], info['exp']) == (*a_pos, 90), 'Alice at {},{} with 90 exp'.format(*a_pos))
    b2.recv_until(of(0x12, a.cid, at=5), what='B sees A back')
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
    servers['bin/gs.py'].start()

    a = login_ok('alice', 'pw1')
    e = char_list(a)
    check(len(e) == 1 and text(e[0][1:11]) == 'Alice', 'Alice is in the char list after the restart')
    info = enter(a, 'Alice')
    check((info['x'], info['y'], info['map'], info['exp']) == (*a_pos, 0, 90),
          'Alice is back at {},{} with 90 exp'.format(*a_pos))
    check((info['money'], info['pk'], info['ctl']) == (31337, 3, 0), 'money 31337 at 36, pk level 3 at 40, ctl at 41')
    bad, res = login('alice', 'nope')
    check(res == 0, 'bad password still rejected')
    bad.s.close()
    b3 = login_ok('bob', 'pw2')
    info = enter(b3, 'Bobby')
    check((info['x'], info['y'], info['exp']) == (*B_SPOT, 90), 'Bobby too')
    a.recv_until(of(0x12, b3.cid, at=5), what='A sees B after the restart')
    check(True, 'A sees B after the restart')


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
    Path(config).write_text(CONFIG.format(db_path))
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
