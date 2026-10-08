"""
Map terrain: the client's Data/World{n+1}/Terrain{n+1}.att, copied to data/terrain. docs/protocol-097.md, Terrain.
"""
import random

SIZE = 256
FILE_SIZE = 3 + SIZE * SIZE
HEADER = b'\x00\xff\xff'

SAFE = 0x01  # safe zone: no attacks, monsters don't enter
OCCUPIED = 0x02  # the client marks the tiles characters stand on at run time, a few files have one left in them
BLOCKED = 0x04
NO_GROUND = 0x08
NOT_WALKABLE = BLOCKED | NO_GROUND  # the client's path finder only steps on tiles below 2, occupied ones aside


class Terrain:
    """256 x 256 tile attributes, index y * 256 + x."""

    def __init__(self, attributes: bytes):
        if len(attributes) != SIZE * SIZE:
            raise ValueError('{} terrain bytes, needs {}'.format(len(attributes), SIZE * SIZE))
        self.attributes = attributes

    @classmethod
    def load(cls, path):
        """Checked like the client does: 0x10003 bytes, header 00 FF FF."""
        with open(path, 'rb') as f:
            data = f.read()
        if len(data) != FILE_SIZE or data[:3] != HEADER:
            raise ValueError('{}: not a terrain file ({} bytes, header {})'.format(path, len(data), data[:3].hex()))
        return cls(data[3:])

    def attribute(self, x, y):
        return self.attributes[y * SIZE + x]

    def walkable(self, x, y):
        return 0 <= x < SIZE and 0 <= y < SIZE and not self.attributes[y * SIZE + x] & NOT_WALKABLE

    def safe(self, x, y):
        return 0 <= x < SIZE and 0 <= y < SIZE and bool(self.attributes[y * SIZE + x] & SAFE)

    def random_spot(self, xs, ys, accept=None):
        """A random walkable tile of the area xs x ys for which accept(x, y) holds, None if there is none."""
        def ok(x, y):
            return self.walkable(x, y) and (accept is None or accept(x, y))

        for _ in range(20):
            x, y = random.choice(xs), random.choice(ys)
            if ok(x, y):
                return x, y
        spots = [(x, y) for x in xs for y in ys if ok(x, y)]
        return random.choice(spots) if spots else None
