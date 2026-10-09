"""
The chaos goblin's machine: items go into its 8 x 4 box with 24 (window 3), 86 mixes them. The mix is the one the
client recognises (0x49b680), at the rate and zen it shows (0x4a7760), from a data file so a test can make them
certain. Results are the usual 0.97 ones. Items left in the box go back into the inventory when the window closes,
those that don't fit stay in the box (stored with the character) and come back on the next entry.
"""
import logging
import random
from dataclasses import dataclass
from mup.model.item import GROUP_SIZE
from mup.packet.server import SItemList, SMixResult, SPickUpResult, STalk
from mup.server import inventory, item as items, shop

logger = logging.getLogger(__name__)

# what the client recognises (0x49b680), its numbers
IMPROPER, CHAOS_WEAPON, INVITATION, PLUS10, PLUS11, DINORANT = 0, 1, 2, 3, 4, 5
LEVELS_DIFFER = -2  # a Devil's eye and key of different levels
NAMES = {'chaos': CHAOS_WEAPON, 'invitation': INVITATION, 'plus10': PLUS10, 'plus11': PLUS11, 'dinorant': DINORANT}
CLIENT = -1  # the data file's value for the client's own rate / zen
RATE_PER_ZEN = 20000  # the chaos weapon mix: 1% per 20000 zen of the items' prices, at most 100%
ZEN_PER_RATE = 10000

HORN_OF_UNIRIA, DINORANT_HORN = 13 * GROUP_SIZE + 2, 13 * GROUP_SIZE + 3
FULL = 255  # a horn of uniria with full life counts
CHAOS_WEAPONS = (2 * GROUP_SIZE + 6, 4 * GROUP_SIZE + 6, 5 * GROUP_SIZE + 7)  # dragon axe, nature bow, lightning staff
FIRST_WINGS = (12 * GROUP_SIZE, 12 * GROUP_SIZE + 1, 12 * GROUP_SIZE + 2)
JEWELS = (shop.JEWEL_OF_CHAOS, shop.JEWEL_OF_BLESS, shop.JEWEL_OF_SOUL)
OPTION_LINES = (shop.DAMAGE_OPTION, shop.MAGIC_OPTION, shop.BLOCK_OPTION, shop.DEFENSE_OPTION)
# the Devil Square invitation by the level of its eye and key (0..5): the client shows 60% for level 1, the rates of
# the 30 answer for levels 2..5 (its own defaults), and the zen by level (0x4a7760). It shows nothing for level 0
# but mixes it, its Devil Square window takes a level 0 invitation for every square: level 1's rate and zen, mup's
INVITATION_RATE = 60
INVITATION_RATES = bytes([80, 75, 70, 60])
INVITATION_ZEN = (10000, 10000, 20000, 40000, 70000)
INVITATION_LEVELS = range(0, 6)


@dataclass(frozen=True)
class MixInfo:
    rate: int  # %, CLIENT: the client's
    zen: int
    luck: int  # % more when the item mixed has luck


def load(path):
    """Mix number -> MixInfo, lines of: name rate zen luck."""
    mixes = {}
    with open(path, encoding='latin-1') as f:
        for line in f:
            v = line.split('//', 1)[0].split()
            if not v or v[0] == 'end':
                continue
            if v[0] not in NAMES:
                raise ValueError('{}: unknown mix {}'.format(path, v[0]))
            mixes[NAMES[v[0]]] = MixInfo(int(v[1]), int(v[2]), int(v[3]))
    return mixes


def recognize(box):
    """The mix the client takes the box for (0x49b680), and the luck it counts (the last item it looked at of level
    9 / 10 or a weapon / armor of level 4 and up)."""
    chaos = plus9 = plus10 = materials = other = unirias = bless = soul = eyes = keys = 0
    eye_level = key_level = 0
    lucky = False
    for slot in sorted(box):
        item = box[slot]
        t, level = item.type, item.level
        looked = False
        if t < 12 * GROUP_SIZE + 3 and level in (9, 10):
            plus9 += level == 9
            plus10 += level == 10
            lucky, looked = False, True
        if t == shop.JEWEL_OF_CHAOS:
            chaos += 1
        elif t == HORN_OF_UNIRIA:
            unirias += item.durability == FULL
        elif t == shop.JEWEL_OF_BLESS:
            bless += 1
        elif t == shop.JEWEL_OF_SOUL:
            soul += 1
        elif t == shop.DEVILS_EYE:
            eyes, eye_level = eyes + 1, level
        elif t == shop.DEVILS_KEY:
            keys, key_level = keys + 1, level
        elif t >= 12 * GROUP_SIZE or level < 4:
            other += 1
        else:
            lucky, looked = False, True
            if any(o in OPTION_LINES for o, _ in shop.options(item)):
                materials += 1
            else:
                other += 1
        if looked and item.luck:
            lucky = True

    count = len(box)
    if count == 3 and chaos == 1 and eyes == 1 and keys == 1:
        if eye_level != key_level:
            return LEVELS_DIFFER, lucky
        return (INVITATION if eye_level in INVITATION_LEVELS else IMPROPER), lucky
    if count == 4 and chaos == 1 and plus9 == 1 and bless == 1 and soul == 1:
        return PLUS10, lucky
    if count == 4 and chaos == 1 and unirias == 3:
        return DINORANT, lucky
    if count == 6 and chaos == 1 and plus10 == 1 and bless == 2 and soul == 2:
        return PLUS11, lucky
    if chaos and materials and not (eyes or keys or unirias or other):
        return CHAOS_WEAPON, lucky
    return IMPROPER, lucky


def rate_and_zen(game, mix, lucky, box):
    """Success rate % and zen of a mix, as the client shows them unless the data file says otherwise."""
    info = game.mixes[mix]
    if mix == CHAOS_WEAPON:
        client = min(100, sum(shop.value(item) for item in box.values()) // RATE_PER_ZEN)
        rate = client if info.rate == CLIENT else info.rate
        zen = client * ZEN_PER_RATE if info.zen == CLIENT else info.zen
    elif mix == INVITATION:
        level = max(1, invitation_level(box))
        client = INVITATION_RATE if level == 1 else INVITATION_RATES[level - 2]
        rate = client if info.rate == CLIENT else info.rate
        zen = INVITATION_ZEN[level - 1] if info.zen == CLIENT else info.zen
    else:
        rate, zen = info.rate, info.zen
    if lucky:
        rate += info.luck
    return min(rate, 100), zen


def invitation_level(box):
    return next(item.level for item in box.values() if item.type == shop.DEVILS_EYE)


def rates(game):
    """The invitation rates for levels 2..5 the 30 answer shows: the data file's, else the client's own."""
    info = game.mixes.get(INVITATION)
    if info is None or info.rate == CLIENT:
        return INVITATION_RATES
    return bytes([min(100, info.rate)] * 4)


def open_box(game, c):
    """c's player talks to the chaos goblin: the window, and the box when the client may show something else."""
    p = c.player
    if p.chaos_box:
        return_items(game, c)
    c.write(STalk(window=STalk.CHAOS_MACHINE, rates=rates(game)))
    if p.chaos_box or c.stale_box:
        # the client shows it with "Chaos combining has failed", the only way to put items in its box
        c.write(SItemList.of(SItemList.CHAOS_BOX, p.chaos_box))
    c.stale_box = False


def return_items(game, c, notify=True):
    """The items in c's player's box go back into the inventory where they fit. notify: the client gets the
    inventory (F3 10) when something moved."""
    p = c.player
    moved = False
    for slot in sorted(p.chaos_box):
        item = p.chaos_box[slot]
        target = inventory.free_slot(p.inventory, item.info)
        if target is None:
            continue
        del p.chaos_box[slot]
        p.inventory[target] = item
        moved = True
    if p.chaos_box:
        logger.warning('%s: no room in the inventory, %s stay in the chaos machine', p.name, list(p.chaos_box.values()))
    if moved and notify:
        inventory.send(c)
    return moved


def is_open(c):
    return c.window is not None and c.window.kind == STalk.CHAOS_MACHINE



def mix(game, c, rng=random):
    """86: c's player mixes what is in the box. Zen first (22 FE), then 86 with the result, after a failure the box
    as it is left (31). A mix mup doesn't make fails with the box untouched: any other answer leaves the client's
    mix button dead, and the window doesn't close with items in the box."""
    p = c.player
    box = p.chaos_box
    kind, lucky = recognize(box)
    if p.dead or not is_open(c):
        logger.debug('%s: mix refused, the machine isn\'t open', p.name)
        c.write(SMixResult(result=SMixResult.REFUSED))
        return False
    if kind not in game.mixes:
        logger.info('%s: no mix of %s', p.name, list(box.values()))
        c.write(SMixResult(result=SMixResult.FAILED))
        c.write(SItemList.of(SItemList.CHAOS_BOX, box))
        return False
    rate, zen = rate_and_zen(game, kind, lucky, box)
    if zen > p.zen:
        c.write(SMixResult(result=SMixResult.NO_ZEN))
        return False
    p.zen -= zen
    c.write(SPickUpResult.zen(p.zen))
    success = rng.randrange(100) < rate
    logger.info('%s mixes %s at %s%% for %s zen: %s, %s', p.name, kind, rate, zen, 'success' if success else 'failed',
                list(box.values()))
    if success:
        result = RESULTS[kind](game, box, rate, rng)
        box.clear()
        box[0] = result
        c.write(SMixResult(result=SMixResult.SUCCESS, item=result.encode()))
        return True
    if kind == CHAOS_WEAPON:
        degrade(box, rng)
    else:
        box.clear()  # +10, +11 and the dinorant lose everything
    c.write(SMixResult(result=SMixResult.FAILED))
    c.write(SItemList.of(SItemList.CHAOS_BOX, box))
    return False


def degrade(box, rng):
    """A failed chaos weapon mix: the jewels are gone, the other items lose levels and maybe a step of their
    option (usual)."""
    for slot, item in list(box.items()):
        if item.type in JEWELS:
            del box[slot]
            continue
        if item.level > 0:
            item.level = rng.randrange(item.level)
        if item.option > 0 and rng.randrange(2) == 0:
            item.option -= 1
        item.durability = min(item.durability, items.max_durability(item))


def chaos_weapon(game, box, rate, rng):
    """A chaos weapon of level 0..4, or first wings when a chaos weapon was mixed. Skill, luck and option by the
    rate (usual)."""
    wings = any(item.type in CHAOS_WEAPONS for item in box.values())
    result = rng.choice(FIRST_WINGS if wings else CHAOS_WEAPONS)
    option = 0
    roll = rng.randrange(100)
    kind = rng.randrange(3)
    if roll < rate // 5 + 4 * (kind + 1):
        option = 3 - kind
    return game.new_item(game.item_info[result], level=0 if wings else rng.randrange(5),
                         skill=not wings and rng.randrange(100) < rate // 5 + 6,
                         luck=rng.randrange(100) < rate // 5 + 4, option=option)


def level_up(game, box, rate, rng):
    """+10 / +11: the +9 / +10 item one level up, full durability."""
    item = next(i for i in box.values() if i.type < 12 * GROUP_SIZE + 3 and i.level in (9, 10))
    item.level += 1
    item.durability = items.max_durability(item)
    return item


def dinorant(game, box, rate, rng):
    return game.new_item(game.item_info[DINORANT_HORN])


def invitation(game, box, rate, rng):
    """A Devil's invitation of the eye and key's level."""
    return game.new_item(game.item_info[shop.DEVILS_INVITATION], level=invitation_level(box))


RESULTS = {CHAOS_WEAPON: chaos_weapon, INVITATION: invitation, PLUS10: level_up, PLUS11: level_up,
           DINORANT: dinorant}
