"""
A player's inventory: the equipment slots and the 8 x 8 grid (mup.model.item), what may go where, moving and using
items. Player.inventory maps the slot of an item (its top left tile in the grid) to the item.
"""
import logging
from mup.model.item import (GRID, GRID_SIZE, RIGHT_HAND, LEFT_HAND, RING, RING2, WINGS, PET, BOLT, ARROWS, GLOW,
                            glow)
from mup.packet.server import SInventory, SLookChange, SLife, SMana, SItemDeleted, SDurability
from mup.server import item as items, skill, stats, view

logger = logging.getLogger(__name__)

GRID_END = GRID + GRID_SIZE * GRID_SIZE
SHOWN = range(PET + 1)  # equipment slots others see change (25), not the pendant and the rings
AMMO = (BOLT, ARROWS)  # may share the hands with a two-handed bow / crossbow


def tiles(slot, info):
    """Grid tiles (0..63) an item of type info covers from slot, None when it sticks out of the grid."""
    x, y = (slot - GRID) % GRID_SIZE, (slot - GRID) // GRID_SIZE
    if x + info.width > GRID_SIZE or y + info.height > GRID_SIZE:
        return None
    return {(y + dy) * GRID_SIZE + x + dx for dy in range(info.height) for dx in range(info.width)}


def taken(inventory, skip=None):
    """Grid tiles covered by the items in the grid but the one in slot skip."""
    used = set()
    for slot, item in inventory.items():
        if slot >= GRID and slot != skip:
            used |= tiles(slot, item.info)
    return used


def fits(inventory, info, slot, skip=None):
    """An item of type info fits the grid from slot, the item in slot skip (the one moving) left out."""
    if not GRID <= slot < GRID_END:
        return False
    t = tiles(slot, info)
    return t is not None and t.isdisjoint(taken(inventory, skip))


def free_slot(inventory, info):
    """The first grid slot, row by row, an item of type info fits in. None when the grid is full."""
    used = taken(inventory)
    for slot in range(GRID, GRID_END):
        t = tiles(slot, info)
        if t is not None and t.isdisjoint(used):
            return slot
    return None


def class_allowed(p, info):
    """The item's class byte: 1 any, 2 second class only. Magic gladiators also wear what wizards or knights may,
    like the client's check."""
    number = p.class_type.value >> 5
    if number == 3:
        return any(info.classes[n] for n in (0, 1, 3))
    allowed = info.classes[number]
    return allowed == 1 or allowed == 2 and bool(p.class_type.value & 0x10)


def can_wear(p, item, slot, skip=None):
    """
    p may put item in equipment slot: its slot (rings either, one-handed weapons also the left hand), its class,
    level and stat requirements, no two-handed weapon sharing the hands but with ammunition. skip: the slot the item
    comes from, not counted.
    """
    wanted = items.slot_class(item.type)
    if wanted is None:
        return False
    if not (slot == wanted or wanted == RING and slot == RING2
            or wanted == RIGHT_HAND and slot == LEFT_HAND and item.info.width == 1):
        return False
    if not class_allowed(p, item.info):
        return False
    r = items.requirements(item)
    if p.level < r.level or p.strength < r.strength or p.agility < r.agility or p.energy < r.energy:
        return False
    if slot in (RIGHT_HAND, LEFT_HAND):
        other_slot = LEFT_HAND if slot == RIGHT_HAND else RIGHT_HAND
        other = p.inventory.get(other_slot) if other_slot != skip else None
        if other is not None:
            if item.info.two_handed and other.type not in AMMO or other.info.two_handed and item.type not in AMMO:
                return False
    return True


def send(c):
    """The whole inventory to c's client (F3 10)."""
    c.write(SInventory.of(c.player.inventory))


def move(game, c, source, target):
    """Moves the item in slot source of c's player to slot target. False when it may not go there."""
    inv = c.player.inventory
    item = inv.get(source)
    if item is None or not 0 <= target < GRID_END:
        return False
    if source == target:
        return True
    if target < GRID:
        if target in inv or not can_wear(c.player, item, target, skip=source):
            return False
    elif not fits(inv, item.info, target, skip=source):
        return False

    del inv[source]
    inv[target] = item
    for slot in (source, target):
        if slot < GRID:
            look_changed(game, c, slot)
    if source < GRID or target < GRID:
        stats.update(c)
        skill.update_weapon_skills(game, c)
    return True


def look_changed(game, c, slot):
    """Equipment slot of c's player changed: the players who see it get the new look."""
    if slot not in SHOWN:
        return
    item = c.player.inventory.get(slot)
    if item is None or slot in (WINGS, PET):
        level = 0
    elif slot == RIGHT_HAND:
        level = GLOW[glow(item.level)]  # the client takes the right hand's level as it is, the others as glow
    else:
        level = glow(item.level)
    packet = SLookChange.of(c.cid, slot, item, level)
    for o in view.viewers(game, c):
        o.write(packet)


def learn(game, c, item):
    """c's player reads a scroll / orb: the class and requirements of the item, as for wearing it. False when it
    can't or knows the skill."""
    p = c.player
    number = skill.taught_by(item)
    r = items.requirements(item)
    if (number not in game.skills or not class_allowed(p, item.info) or p.level < r.level or p.strength < r.strength
            or p.agility < r.agility or p.energy < r.energy):
        logger.info('%s can\'t learn skill %s from %s', p.name, number, item)
        return False
    return skill.learn(c, number)


def use(game, c, slot):
    """
    c's player uses (right clicks) the item in slot: potions heal. The client locks item use until the answer, the
    count update or the delete unlocks it.
    """
    p = c.player
    item = p.inventory.get(slot)
    if not p.dead and item is not None and slot >= GRID and skill.taught_by(item) is not None:
        if learn(game, c, item):
            del p.inventory[slot]
            c.write(SItemDeleted(slot=slot))
        else:
            c.write(SLife(type=SLife.UNLOCK, value=0))
        return
    if p.dead or item is None or slot < GRID or not (item.type in items.HEALING or item.type in items.MANA):
        # todo jewels (roadmap M5)
        c.write(SLife(type=SLife.UNLOCK, value=0))
        return

    if item.type in items.HEALING:
        heal = max(0, item.info.value * 10 - p.level * 2) + p.max_life * items.HEALING[item.type] // 100
        p.life = min(p.max_life, p.life + heal)
        c.write(SLife(value=p.life))
    else:
        p.mana = min(p.max_mana, p.mana + p.max_mana * items.MANA[item.type] // 100)
        c.write(SMana(value=p.mana))

    item.durability -= 1
    if item.durability <= 0:
        del p.inventory[slot]
        c.write(SItemDeleted(slot=slot))
    else:
        c.write(SDurability(slot=slot, durability=item.durability))
