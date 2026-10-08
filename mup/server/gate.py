"""
Gates from the client's Data/Gate.bmd (copied to data/), the client decides when to send the move request with them.
docs/protocol-097.md, Gates.
"""
import logging
from dataclasses import dataclass
from mup.model.player import CharacterClass
from mup.packet.server import SMapMove

logger = logging.getLogger(__name__)

GATES = 100
ENTRY_SIZE = 9
KEY = bytes([0xFC, 0xCF, 0xAB])

# kinds
TOWN = 0  # a place to move to: start and respawn areas, warp targets
ENTRANCE = 1  # stepping on it sends the move request, it leads to target
EXIT = 2  # where an entrance puts the player


@dataclass(frozen=True)
class Gate:
    number: int
    kind: int
    map_id: int
    xs: range
    ys: range
    target: int  # gate an entrance leads to
    direction: int
    level: int  # minimum level, magic gladiators need two thirds of it

    def contains(self, map_id, x, y):
        return map_id == self.map_id and x in self.xs and y in self.ys

    def min_level(self, magic_gladiator):
        # the client: level * 2 / 3 for class number 3
        return self.level * 2 // 3 if magic_gladiator else self.level


def load(path):
    """Gate number -> Gate, the empty entries left out."""
    with open(path, 'rb') as f:
        data = f.read()
    if len(data) != GATES * ENTRY_SIZE:
        raise ValueError('{}: {} bytes, needs {}'.format(path, len(data), GATES * ENTRY_SIZE))

    data = bytes(b ^ KEY[i % 3] for i, b in enumerate(data))
    gates = {}
    for n in range(GATES):
        kind, map_id, x1, y1, x2, y2, target, direction, level = data[n * ENTRY_SIZE:(n + 1) * ENTRY_SIZE]
        if any((kind, map_id, x1, y1, x2, y2, target, direction, level)):
            gates[n] = Gate(n, kind, map_id, range(x1, x2 + 1), range(y1, y2 + 1), target, direction, level)
    return gates


def enter(game, c, number):
    """c's player stepped on entrance gate number: it goes to the gate's target. False when it can't."""
    p = c.player
    g = game.gates.get(number)
    if g is None or g.kind != ENTRANCE or g.target not in game.gates:
        logger.warning('%s: no entrance gate %s', p.name, number)
        return False
    # the client sends the request when it stands on the gate, the server's position is the end of the walk
    if not any(g.contains(p.map_id, x, y) for x, y in [(p.x, p.y)] + p.walk_path):
        logger.warning('%s at %s %s,%s isn\'t at gate %s', p.name, p.map_id, p.x, p.y, number)
        return False
    if p.level < g.min_level(p.class_type.base == CharacterClass.MAGIC_GLADIATOR):
        logger.info('%s is level %s, gate %s needs %s', p.name, p.level, number, g.level)
        return False

    target = game.gates[g.target]
    map_id, x, y = game.gate_spot(g.target)
    logger.info('%s goes through gate %s to %s %s,%s', p.name, number, map_id, x, y)
    game.relocate(c, map_id, x, y, target.direction,
                  lambda p: SMapMove(map=p.map_id, x=p.x, y=p.y, direction=p.direction))
    return True
