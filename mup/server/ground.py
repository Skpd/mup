"""
Items and zen on the ground: dropped by players and monsters, picked up, gone after a while. The client keeps ground
items in 1000 slots of its own, their ids are those slots.
"""
import logging
from collections import deque
from mup.model.item import GRID, GroundItem
from mup.packet.server import SPickUpResult
from mup.server import inventory, skill, stats, view
from mup.server.world import distance

logger = logging.getLogger(__name__)

IDS = 1000
LIFETIME = 60.0  # seconds an item stays on the ground, mup's choice
OWNER_TIME = 10.0  # seconds the killer alone may pick up a monster's drop, mup's choice
PICK_UP_RANGE = 3  # tiles, the client sends pick ups from 1.5 tiles
DROP_RANGE = 3  # tiles from the player a dropped item may land, farther away it lands on the player's tile
SPREAD = 2  # tiles around the first spot the items of one kill spread to
MAX_ZEN = 2_000_000_000


class Ground:
    """The ground items of all maps by id."""

    def __init__(self):
        self.items = {}
        self.free = deque(range(IDS))

    def __len__(self):
        return len(self.items)


def place(game, map_id, x, y, item=None, zen=0, owner=None):
    """Puts an item (or zen) on a map tile, shown falling to the players near. None when all ids are taken."""
    ground = game.ground
    if not ground.free:
        logger.warning('No free ground item id, %s on map %s is lost', item or '{} zen'.format(zen), map_id)
        return None
    now = game.now
    g = GroundItem(ground.free.popleft(), map_id, x, y, item, zen, owner, now + OWNER_TIME if owner else 0.0,
                   now + LIFETIME)
    ground.items[g.id] = g
    game.maps[map_id].add_item(g)
    view.item_appeared(game, g)
    return g


def remove(game, g):
    """Takes an item off the ground."""
    view.item_removed(game, g)
    game.maps[g.map_id].remove_item(g)
    del game.ground.items[g.id]
    game.ground.free.append(g.id)


def tick(game, now):
    for g in [g for g in game.ground.items.values() if g.expires_at <= now]:
        remove(game, g)


def spots(game, map_id, x, y):
    """Free tiles for the items of one kill: x, y first, then the walkable tiles around without an item."""
    m = game.maps[map_id]
    for d in range(SPREAD + 1):
        for dy in range(-d, d + 1):
            for dx in range(-d, d + 1):
                tx, ty = x + dx, y + dy
                if max(abs(dx), abs(dy)) == d and m.terrain.walkable(tx, ty) and not m.items.near(tx, ty, 0):
                    yield tx, ty


def drop_loot(game, map_id, x, y, loot, owner):
    """A monster's loot (Items and zen amounts) on the ground around x, y, the owner picks up first."""
    free = spots(game, map_id, x, y)
    for thing in loot:
        tx, ty = next(free, (x, y))
        if isinstance(thing, int):
            place(game, map_id, tx, ty, zen=thing, owner=owner)
        else:
            place(game, map_id, tx, ty, item=thing, owner=owner)


def drop(game, c, slot, x, y):
    """c's player drops the item in slot on x, y, or on its own tile when x, y is too far or not walkable."""
    p = c.player
    item = p.inventory.get(slot)
    if p.dead or item is None:
        return False
    m = game.maps[p.map_id]
    if distance(x, y, p.x, p.y) > DROP_RANGE or not m.terrain.walkable(x, y):
        x, y = p.x, p.y
    del p.inventory[slot]
    if slot < GRID:
        inventory.look_changed(game, c, slot)
        stats.update(c)
        skill.update_weapon_skills(game, c)
    logger.debug('%s drops %s at %s,%s', p.name, item, x, y)
    place(game, p.map_id, x, y, item=item)
    return True


def pick_up(game, c, item_id):
    """c's player picks up a ground item: into the first free grid slot, zen into its money. Answers with 22."""
    p = c.player
    g = game.ground.items.get(item_id)
    if (p.dead or g is None or g.map_id != p.map_id or distance(g.x, g.y, p.x, p.y) > PICK_UP_RANGE
            or g.owner is not None and g.owner is not c and game.now < g.owner_until):
        c.write(SPickUpResult.failed())
        return

    if g.item is None:
        if p.zen + g.zen > MAX_ZEN:
            c.write(SPickUpResult.failed())
            return
        p.zen += g.zen
        c.write(SPickUpResult.zen(p.zen))
    else:
        slot = inventory.free_slot(p.inventory, g.item.info)
        if slot is None:
            c.write(SPickUpResult.failed())
            return
        p.inventory[slot] = g.item
        c.write(SPickUpResult.item(slot, g.item))
    logger.debug('%s picks up %s', p.name, g.item or '{} zen'.format(g.zen))
    remove(game, g)
