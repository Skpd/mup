"""Maps 0..10: terrain and who is where on it."""
import os
from collections import Counter, defaultdict
from mup.server.terrain import Terrain

MAP_NAMES = {
    0: 'Lorencia', 1: 'Dungeon', 2: 'Devias', 3: 'Noria', 4: 'Lost Tower', 5: 'Exile', 6: 'Arena', 7: 'Atlans',
    8: 'Tarkan', 9: 'Devil Square', 10: 'Icarus',
}
VIEW_RANGE = 16  # objects within this many tiles (both axes) are in view


def distance(x1, y1, x2, y2):
    """Tiles between two points, a diagonal step counts as one."""
    return max(abs(x1 - x2), abs(y1 - y2))


class Grid:
    """Objects by position in 8 x 8 tile cells, to find the ones near a point without looking at all of them."""
    CELL_BITS = 3

    def __init__(self):
        self.cells = defaultdict(set)
        self.positions = {}

    def __contains__(self, obj):
        return obj in self.positions

    def __len__(self):
        return len(self.positions)

    def __iter__(self):
        return iter(list(self.positions))

    def add(self, obj, x, y):
        if obj in self.positions:
            self.remove(obj)
        self.positions[obj] = x, y
        self.cells[x >> self.CELL_BITS, y >> self.CELL_BITS].add(obj)

    def remove(self, obj):
        x, y = self.positions.pop(obj)
        key = x >> self.CELL_BITS, y >> self.CELL_BITS
        cell = self.cells[key]
        cell.discard(obj)
        if not cell:
            del self.cells[key]

    def move(self, obj, x, y):
        ox, oy = self.positions[obj]
        if (ox >> self.CELL_BITS, oy >> self.CELL_BITS) == (x >> self.CELL_BITS, y >> self.CELL_BITS):
            self.positions[obj] = x, y
        else:
            self.add(obj, x, y)

    def near(self, x, y, within):
        """Objects at most within tiles away from x, y."""
        b = self.CELL_BITS
        found = []
        for cx in range((x - within) >> b, ((x + within) >> b) + 1):
            for cy in range((y - within) >> b, ((y + within) >> b) + 1):
                for obj in self.cells.get((cx, cy), ()):
                    ox, oy = self.positions[obj]
                    if abs(ox - x) <= within and abs(oy - y) <= within:
                        found.append(obj)
        return found


class Map:
    """
    One map: its terrain, the connections in game on it, its living monsters and the items on the ground. Positions
    change through the methods here, which keep the objects and the grids in step.
    """

    def __init__(self, number, terrain: Terrain):
        self.number = number
        self.name = MAP_NAMES[number]
        self.terrain = terrain
        self.players = Grid()  # connections
        self.monsters = Grid()  # living monsters
        self.occupied = Counter()  # tiles living monsters stand on
        self.items = Grid()  # GroundItems

    def __repr__(self):
        return '<Map {} {}>'.format(self.number, self.name)

    def add_player(self, c):
        self.players.add(c, c.player.x, c.player.y)

    def move_player(self, c, x, y):
        c.player.x, c.player.y = x, y
        self.players.move(c, x, y)

    def remove_player(self, c):
        if c in self.players:
            self.players.remove(c)

    def add_monster(self, m):
        self.monsters.add(m, m.x, m.y)
        self.occupied[m.x, m.y] += 1

    def move_monster(self, m, x, y):
        self._vacate(m.x, m.y)
        m.x, m.y = x, y
        self.monsters.move(m, x, y)
        self.occupied[x, y] += 1

    def remove_monster(self, m):
        if m in self.monsters:
            self.monsters.remove(m)
            self._vacate(m.x, m.y)

    def _vacate(self, x, y):
        self.occupied[x, y] -= 1
        if self.occupied[x, y] <= 0:
            del self.occupied[x, y]

    def add_item(self, g):
        self.items.add(g, g.x, g.y)

    def remove_item(self, g):
        if g in self.items:
            self.items.remove(g)

    def monster_can_stand(self, x, y):
        """Walkable, outside the safe zone and free of other monsters."""
        t = self.terrain
        return t.walkable(x, y) and not t.safe(x, y) and (x, y) not in self.occupied


def load_maps(directory):
    """Map number -> Map, terrains from directory/Terrain{n+1}.att like the client's World{n+1} folders."""
    return {n: Map(n, Terrain.load(os.path.join(directory, 'Terrain{}.att'.format(n + 1)))) for n in MAP_NAMES}
