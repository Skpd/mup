"""
Scripted 0.97 client: starts the connect and game server, then plays them over real sockets the way the
client does (same keys, encryption, xor and packet layouts, see docs/protocol-097.md) and checks the answers.

usage: ./venv/bin/python tests/client.py
Exits non zero on the first failed check and prints the end of the server logs.
Ports 44405 and 55901 must be free, stop running servers first.
"""
import socket
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

HOST = '127.0.0.1'
CS_PORT = 44405
GS_PORT = 55901


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
        self.s.settimeout(timeout)
        while True:
            if self.buf:
                header = 3 if self.buf[0] in (0xC2, 0xC4) else 2
                if len(self.buf) >= header:
                    size = (self.buf[1] << 8 | self.buf[2]) if header == 3 else self.buf[1]
                    if len(self.buf) >= size:
                        p = Base(self.buf[:size])
                        del self.buf[:size]
                        if p[0] in (0xC3, 0xC4):
                            p = self.crypt.decrypt(p)
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


def damage(p):
    """Damage value of a 0x15 packet, the top 3 bits are colour flags."""
    return (p[5] & 0x1F) << 8 | p[6]


def login_and_enter(account, password, char_name, class_type=0, create=True):
    """class_type as the create screen sends it: class number << 2 (0 dw, 16 dk, 32 elf, 48 mg)"""
    cs = Conn(CS_PORT, 'cs-' + account)
    p = cs.recv_until(key(0x00, 0x01), what='hello')
    check(bytes(p) == bytes([0xC1, 0x04, 0x00, 0x01]), 'cs hello')
    cs.send([0xC1, 0, 0xF4, 0x02])
    p = cs.recv_until(key(0xF4, 0x02), what='server list')
    check(p[0] == 0xC2 and p[5] == 1 and p[6] | p[7] << 8 == 0, 'server list has server 0: ' + p.hex(' '))
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
    if p[4] != 1:
        return gs, p[4]
    check(True, 'login ok')
    gs.joined = True

    gs.send([0xC1, 0, 0xF3, 0x00])
    p = gs.recv_until(key(0xF3, 0x00), what='char list')
    if create:
        check(p[4] == 0, 'empty char list')
        gs.send([0xC1, 0, 0xF3, 0x01, *name10(char_name), class_type])
        p = gs.recv_until(key(0xF3, 0x01), what='char created')
        check(p[4] == 1 and bytes(p[5:15]).rstrip(b'\0').decode() == char_name and p[15] == 0,
              'char created: ' + p.hex(' '))
        gs.send([0xC1, 0, 0xF3, 0x00])
        p = gs.recv_until(key(0xF3, 0x00), what='char list 2')
        check(p[4] == 1 and len(p) == 5 + 26, 'char list has 1 entry of 26 bytes')
        e = p[5:]
        check(e[0] == 0 and bytes(e[1:11]).rstrip(b'\0').decode() == char_name and e[12] | e[13] << 8 == 1
              and e[15] == class_type << 1 and bytes(e[16:26]) == bytes([0xFF] * 5 + [0, 0, 0, 0xF8, 0]),
              'char list entry ' + e.hex(' '))

    gs.send([0xC1, 0, 0xF3, 0x03, *name10(char_name)])
    p = gs.recv_until(key(0xF3, 0x03), what='char info')
    x, y, map_id, _, exp, next_exp = struct.unpack('<4B2I', bytes(p[4:16]))
    # todo money (36) and pk level (40) once stats.py sends the client's layout, docs/roadmap.md M0
    check(not create or (x, y, map_id, exp, next_exp) == (128, 188, 0, 0, 100),
          'char info x{} y{} map{} exp {}/{}'.format(x, y, map_id, exp, next_exp))
    gs.recv_until(key(0xF3, 0x10), what='inventory')
    p = gs.recv_until(of(0x12, gs.cid, at=5), what='meet self')
    check(bytes(p[23:33]).rstrip(b'\0').decode() == char_name, 'meet self, name at entry + 18')
    p = gs.recv_until(key(0xF3, 0x11), what='skill list')
    print('  skills', [p[5 + i * 3 + 1] for i in range(p[4])])
    return gs, 1


def play():
    print('player A (dark wizard)')
    a, _ = login_and_enter('alice', 'pw1', 'Alice', 0)
    p = a.recv_until(key(0x13), what='meet monster')
    mob = p[5] << 8 | p[6]
    mob_xy = (p[11], p[12])
    check(mob == 0x0F and p[7] == 6 and mob_xy == (127, 189), 'meet monster cid {} type {} at {}'.format(mob, p[7], mob_xy))

    print('wrong password')
    bad, res = login_and_enter('alice', 'nope', 'Alice', create=False)
    check(res == 0, 'bad password rejected')
    bad.s.close()

    print('player B (dark knight)')
    b, _ = login_and_enter('bob', 'pw2', 'Bobby', 16)
    b.recv_until(of(0x12, a.cid, at=5), what='B sees A')
    check(True, 'B sees A on join')
    p = a.recv_until(of(0x12, b.cid, at=5), what='A sees B')
    check(p[9] == 32, 'A sees B as a dark knight (class byte 32)')

    print('framing: two packets in one write, then one split in halves')
    a.send_raw(a.build(walk(128, 188, [3, 3, 3], 3)) + a.build(walk(131, 188, [5], 5)))
    p = b.recv_until(of(0x10, a.cid), what='first move')
    check((p[5], p[6], p[7]) == (131, 188, 3 << 4), 'B sees A walk to 131,188 facing 3')
    p = b.recv_until(of(0x10, a.cid), what='second move')
    check((p[5], p[6]) == (131, 189), 'B sees A walk to 131,189')
    half = a.build(walk(131, 189, [7], 7))
    a.send_raw(half[:3])
    time.sleep(0.2)
    a.send_raw(half[3:])
    p = b.recv_until(of(0x10, a.cid), what='split move')
    check((p[5], p[6]) == (130, 189), 'split packet reassembled')

    print('walk out of view and back')
    a.send(walk(130, 189, [1] * 15, 1))  # 15 steps north, 130,174
    a.send(walk(130, 174, [1] * 15, 1))  # 130,159, 29 tiles from B
    b.recv_until(of(0x14, a.cid, at=4), what='B clears A')
    check(True, 'B lost A from view')
    a.recv_until(of(0x14, b.cid, at=4), what='A clears B')
    a.recv_until(of(0x14, mob, at=4), what='A clears mob')
    check(True, 'A lost B and the monster from view')
    a.send(walk(130, 159, [5] * 15, 5))  # back to 130,174
    p = b.recv_until(of(0x12, a.cid, at=5), what='B meets A again')
    check((p[7], p[8]) == (130, 174), 'B sees A again at 130,174')
    a.recv_until(of(0x12, b.cid, at=5), what='A meets B again')
    a.recv_until(of(0x13, mob, at=5), what='A meets mob again')
    check(True, 'A sees B and the monster again')
    a.send(walk(130, 174, [5] * 14, 5))  # 130,188
    b.recv_until(lambda p: of(0x10, a.cid)(p) and (p[5], p[6]) == (130, 188), what='walk back')
    check(True, 'B sees A walk to 130,188')

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
    b2, _ = login_and_enter('bob', 'pw2', 'Bobby', create=False)
    check(b2.cid != b.cid, 'new connection gets a new cid {}'.format(b2.cid))
    a.recv_until(of(0x12, b2.cid, at=5), what='A sees B again')
    check(True, 'A sees B back')


def port_open(port):
    try:
        socket.create_connection((HOST, port), timeout=0.2).close()
        return True
    except OSError:
        return False


def main():
    if port_open(CS_PORT) or port_open(GS_PORT):
        print('ports {} / {} are in use, stop the running servers first'.format(CS_PORT, GS_PORT))
        return 2

    logs = {}
    servers = []
    try:
        for script in ('bin/cs.py', 'bin/gs.py'):
            log = tempfile.NamedTemporaryFile('w+', prefix=Path(script).stem + '-', suffix='.log', delete=False)
            logs[script] = log
            servers.append(subprocess.Popen([sys.executable, '-u', script], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT))

        deadline = time.time() + 10
        while not (port_open(CS_PORT) and port_open(GS_PORT)):
            if time.time() > deadline or any(s.poll() is not None for s in servers):
                raise AssertionError('servers did not start')
            time.sleep(0.1)

        play()
        print('ALL OK')
        return 0
    except (AssertionError, EOFError, OSError) as e:
        print('FAILED:', e)
        for script, log in logs.items():
            log.flush()
            print('--- {} ({})'.format(script, log.name))
            print(''.join(Path(log.name).read_text(errors='replace').splitlines(True)[-30:]))
        return 1
    finally:
        for s in servers:
            s.terminate()
            s.wait(5)


if __name__ == '__main__':
    sys.exit(main())
