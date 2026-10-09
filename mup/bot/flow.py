"""
Flow fields for long walks: the steps from every tile of a map to the nearest tile of a target area (a gate, the
safe zone, a hunting ground), over the tiles a bot walks on. A bot walks downhill. One field is about 65 000 tiles
looked at once, the fields are kept per map and target (Flows) and shared by the bots. Between maps, routes over the
gates (Flows.routes).
"""
import heapq
from array import array
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Tuple
from mup.bot import motor
from mup.bot.career import CELL
from mup.packet.client_packet.move import STEPS
from mup.server import gate

SIZE = 256
FAR = 0xFFFF  # not reachable
KEEP = 128  # fields kept, the least used go
GATE_STEPS = round((motor.MAP_LOAD + motor.GATE_PAUSE) / motor.STEP_TIME)  # a gate's 1C and loading, in steps


@dataclass(frozen=True)
class Route:
    """The way to the arrival area of an exit gate: the entrance gates in order and the steps walked, each gate
    counting GATE_STEPS."""
    steps: int
    gates: Tuple[int, ...]
    arrival: int  # the exit gate


def walk_mask(game, map_id):
    """1 for the tiles of map_id a bot walks on: walkable for players, but not the entrance gates, the client would
    go through them (a walk to a gate ends on it, the target area of a field may be one)."""
    terrain = game.maps[map_id].terrain
    mask = bytearray(1 if terrain.walkable(i & 0xFF, i >> 8) else 0 for i in range(SIZE * SIZE))
    for g in game.gates.values():
        if g.kind == gate.ENTRANCE and g.map_id == map_id:
            for y in g.ys:
                for x in g.xs:
                    if 0 <= x < SIZE and 0 <= y < SIZE:
                        mask[y * SIZE + x] = 0
    return mask


class FlowField:
    """Steps to the nearest of targets ((x, y) tiles, those not walkable left out) from every tile mask lets a bot
    walk on, a diagonal step counting one like in the walk packet."""

    def __init__(self, mask, targets, walkable=None):
        dist = array('H', [FAR]) * (SIZE * SIZE)
        queue = deque()
        for x, y in targets:
            i = y * SIZE + x
            if 0 <= x < SIZE and 0 <= y < SIZE and dist[i] == FAR and (walkable is None or walkable(x, y)):
                dist[i] = 0
                queue.append(i)
        left = (-SIZE - 1, -1, SIZE - 1)
        right = (-SIZE + 1, 1, SIZE + 1)
        middle = (-SIZE, SIZE)
        last = SIZE * SIZE
        pop, push = queue.popleft, queue.append
        while queue:
            i = pop()
            d = dist[i] + 1
            x = i & 0xFF
            for offsets in (middle, left if x > 0 else (), right if x < SIZE - 1 else ()):
                for o in offsets:
                    j = i + o
                    if 0 <= j < last and dist[j] == FAR and mask[j]:
                        dist[j] = d
                        push(j)
        self.dist = dist

    def distance(self, x, y):
        """Steps from x, y to the target area, None when it can't be reached from there."""
        if not (0 <= x < SIZE and 0 <= y < SIZE):
            return None
        d = self.dist[y * SIZE + x]
        return None if d == FAR else d

    def path(self, x, y, steps):
        """Up to steps tiles downhill from x, y (not included), [] at the target or where it can't be reached. Ties
        go on in the direction of the last step, then in STEPS order: walks run straight where they can."""
        dist = self.dist
        path = []
        d = self.distance(x, y)
        if d is None:
            return path
        last = None
        while d > 0 and len(path) < steps:
            best = None
            for k in ([last] if last is not None else []) + list(range(len(STEPS))):
                dx, dy = STEPS[k]
                nx, ny = x + dx, y + dy
                if 0 <= nx < SIZE and 0 <= ny < SIZE and dist[ny * SIZE + nx] == d - 1:
                    best = k
                    break
            if best is None:
                break
            last = best
            x, y = x + STEPS[best][0], y + STEPS[best][1]
            d -= 1
            path.append((x, y))
        return path


class Flows:
    """The fields of a game by map, target key and the cells kept out, made when first asked for. Also the walk
    masks."""

    def __init__(self, game):
        self.game = game
        self.masks = {}  # map -> mask
        self.blocked = OrderedDict()  # (map, cells kept out) -> mask
        self.outside = {}  # map -> cell -> tile indexes outside the safe zone
        self.steppers = {}
        self.gates = {}
        self.fields = OrderedDict()
        self.made = 0  # fields computed, for the report

    def mask(self, map_id, blocked=frozenset()):
        """The walk mask of map_id, without the tiles outside the safe zone of the blocked cells (mup.bot.career
        cells): where monsters would kill the bot."""
        if map_id not in self.masks:
            self.masks[map_id] = walk_mask(self.game, map_id)
        if not blocked:
            return self.masks[map_id]
        k = map_id, blocked
        mask = self.blocked.get(k)
        if mask is None:
            mask = self.blocked[k] = bytearray(self.masks[map_id])
            cells = self.cells(map_id)
            for cell in blocked:
                for i in cells.get(cell, ()):
                    mask[i] = 0
            if len(self.blocked) > KEEP:
                self.blocked.popitem(last=False)
        else:
            self.blocked.move_to_end(k)
        return mask

    def cells(self, map_id):
        """(cx, cy) -> the tile indexes of a cell outside the safe zone, what blocking a cell takes out."""
        if map_id not in self.outside:
            terrain = self.game.maps[map_id].terrain
            cells = self.outside[map_id] = {}
            for y in range(SIZE):
                for x in range(SIZE):
                    if not terrain.safe(x, y):
                        cells.setdefault((x // CELL, y // CELL), []).append(y * SIZE + x)
        return self.outside[map_id]

    def walkable(self, map_id, blocked=frozenset()):
        """can_step(x, y) for find_path: the tiles a bot walks on, the blocked cells left out."""
        k = map_id, blocked
        stepper = self.steppers.get(k)
        if stepper is None:
            mask = self.mask(map_id, blocked)
            stepper = self.steppers[k] = lambda x, y: 0 <= x < SIZE and 0 <= y < SIZE and mask[y * SIZE + x] == 1
            if len(self.steppers) > KEEP:
                self.steppers.pop(next(iter(self.steppers)))
        return stepper

    def entrances(self, map_id):
        """The entrance gates of map_id."""
        if map_id not in self.gates:
            self.gates[map_id] = [g for g in self.game.gates.values() if g.kind == gate.ENTRANCE and g.map_id == map_id]
        return self.gates[map_id]

    def field(self, map_id, key, targets, blocked=frozenset()):
        """The field of map_id to target key around the blocked cells, targets() gives its tiles when it has to be
        made."""
        k = map_id, key, blocked
        f = self.fields.get(k)
        if f is None:
            terrain = self.game.maps[map_id].terrain
            f = self.fields[k] = FlowField(self.mask(map_id, blocked), targets(), terrain.walkable)
            self.made += 1
            if len(self.fields) > KEEP:
                self.fields.popitem(last=False)
        else:
            self.fields.move_to_end(k)
        return f

    def from_tile(self, map_id, x, y, blocked=frozenset()):
        """A field to x, y around the blocked cells, not kept: its distances are the steps from x, y to
        everywhere."""
        return FlowField(self.mask(map_id, blocked), [(x, y)], self.game.maps[map_id].terrain.walkable)

    def gate(self, number, blocked=frozenset()):
        """To the area of entrance gate number around the blocked cells: a walk down it ends on the gate."""
        g = self.game.gates[number]
        return self.field(g.map_id, ('gate', number), lambda: [(x, y) for y in g.ys for x in g.xs], blocked)

    def arrival(self, number, blocked=frozenset()):
        """To the area of exit gate number, where its entrance puts a player, around the blocked cells: its distances
        are the steps from there to everywhere."""
        g = self.game.gates[number]
        return self.field(g.map_id, ('arrival', number), lambda: [(x, y) for y in g.ys for x in g.xs], blocked)

    def routes(self, map_id, x, y, level, magic_gladiator=False, blocked=frozenset()):
        """Exit gate number -> Route: the fewest steps from x, y of map_id (around its blocked cells) through the
        entrances a player of level may take (the client's rule, Gate.min_level) to every arrival area they lead
        to."""
        gates = self.game.gates
        found = {}
        heap = [(0, (), map_id, None)]  # steps, entrances taken, map, exit gate it arrived at (None: at x, y)
        while heap:
            steps, path, m, at = heapq.heappop(heap)
            if at is not None:
                if at in found:
                    continue
                found[at] = Route(steps, path, at)
                g = gates[at]
                starts = [(tx, ty) for ty in g.ys for tx in g.xs]
            else:
                starts = [(x, y)]
            for e in self.entrances(m):
                if e.target not in gates or e.target in found or level < e.min_level(magic_gladiator):
                    continue
                field = self.gate(e.number, blocked if at is None else frozenset())
                d = min((d for d in (field.distance(tx, ty) for tx, ty in starts) if d is not None), default=None)
                if d is not None:
                    heapq.heappush(heap, (steps + d + GATE_STEPS, path + (e.number,), gates[e.target].map_id,
                                          e.target))
        return found

    def safe(self, map_id, blocked=frozenset()):
        """To the safe zone of map_id (its towns) around the blocked cells."""
        terrain = self.game.maps[map_id].terrain
        return self.field(map_id, 'safe', lambda: [(x, y) for y in range(SIZE) for x in range(SIZE)
                                                   if terrain.safe(x, y)], blocked)
