"""
Jewels: the client sends 26 with the jewel's slot and the target's when a jewel held is dropped on an item of the
inventory grid (0x493dc0, after its own checks: a weapon, armor or first wings, bless up to +5, soul up to +8). The
answer is F3 14 with the item as it is now (the jewel leaves the cursor) and 28 for the jewel, which unlocks item
use. Rates and limits are the usual 0.97 ones.
"""
import logging
import random
from mup.model.item import GROUP_SIZE, GRID, BOLT, ARROWS
from mup.packet.server import SItemChanged, SItemDeleted, SLife
from mup.server import item as items, shop

logger = logging.getLogger(__name__)

JEWELS = (shop.JEWEL_OF_BLESS, shop.JEWEL_OF_SOUL, shop.JEWEL_OF_LIFE)
TARGETS = 12 * GROUP_SIZE + 3  # types below: weapons, armor, the first wings
BLESS_LEVEL = 6  # bless takes an item up to it, soul to 9
SOUL_LEVEL = 9
SOUL_RATE, SOUL_LUCK = 50, 25  # %
SOUL_RESET = 7  # a failed soul from this level takes the item to +0, below one level down
LIFE_OPTION = 4  # +16, the client prices no higher option
LIFE_RATE = 50


def is_jewel(item):
    return item is not None and item.type in JEWELS


def apply(game, c, slot, target, rng=random):
    """26: c's player puts the jewel of slot on the item of grid slot target. Refused: the jewel goes back to its
    slot (F3 14) and item use is unlocked."""
    p = c.player
    jewel = p.inventory.get(slot)
    item = p.inventory.get(target)
    if p.dead or not is_jewel(jewel) or slot < GRID or target < GRID or item is None or slot == target \
            or not upgrade(jewel, item, rng):
        logger.debug('%s: %s on slot %s refused', p.name, jewel, target)
        if jewel is not None:
            c.write(SItemChanged(slot=slot, item=jewel.encode()))
        c.write(SLife(type=SLife.UNLOCK, value=0))
        return False
    del p.inventory[slot]
    logger.info('%s puts %s on %s', p.name, jewel.info.name, item)
    c.write(SItemChanged(slot=target, item=item.encode()))
    c.write(SItemDeleted(slot=slot))
    return True


def upgrade(jewel, item, rng):
    """What the jewel does to the item, False when it can't (the jewel stays)."""
    if item.type >= TARGETS or item.type in (BOLT, ARROWS):
        return False
    if jewel.type == shop.JEWEL_OF_BLESS:
        if item.level >= BLESS_LEVEL:
            return False
        item.level += 1
    elif jewel.type == shop.JEWEL_OF_SOUL:
        if item.level >= SOUL_LEVEL:
            return False
        if rng.randrange(100) < SOUL_RATE + (SOUL_LUCK if item.luck else 0):
            item.level += 1
        else:
            item.level = 0 if item.level >= SOUL_RESET else max(0, item.level - 1)
    else:
        if item.option >= LIFE_OPTION:
            return False
        item.option = item.option + 1 if rng.randrange(100) < LIFE_RATE else 0
    item.durability = items.max_durability(item)
    item.wear = 0
    return True

