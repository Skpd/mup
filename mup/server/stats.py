"""
What a player's class, level, stats and worn items give (Player.values): damage, wizardry damage, attack rate and
speeds, defense and defense rate as the client computes them for its character window (Character values in
docs/protocol-097.md, client 0x45c9f0), so the server hits with what the window shows. Then the excellent options
the client doesn't count (life, mana, damage decrease, ...) and luck, mup's way of applying them.
"""
from mup.model.item import (GROUP_SIZE, BOLT, ARROWS, RIGHT_HAND, LEFT_HAND, HELM, ARMOR, PANTS, GLOVES, BOOTS, WINGS,
                            PENDANT, RING, RING2)
from mup.model.player import CombatValues
from mup.packet.server import SLife, SMana, SPointResult
from mup.server.item import level_bonus, wear_factor, worn

DW, DK, ELF, MG = range(4)  # class number, CharacterClass >> 5

STAFFS = range(5 * GROUP_SIZE, 6 * GROUP_SIZE)
SHIELDS = range(6 * GROUP_SIZE, 7 * GROUP_SIZE)
ARMOR_TYPES = range(7 * GROUP_SIZE, 12 * GROUP_SIZE)
# bows in the left hand, crossbows in the right: the damage comes from agility
LEFT_BOWS = set(range(4 * GROUP_SIZE, 4 * GROUP_SIZE + 7)) | {4 * GROUP_SIZE + 17}
RIGHT_BOWS = set(range(4 * GROUP_SIZE + 8, 4 * GROUP_SIZE + 15)) | set(range(4 * GROUP_SIZE + 16, 5 * GROUP_SIZE))
WINGS_OF_ELF, WINGS_OF_HEAVEN, WINGS_OF_SATAN = (12 * GROUP_SIZE + n for n in range(3))
RINGS_EXC = (13 * GROUP_SIZE + 8, 13 * GROUP_SIZE + 9)  # rings with the armor excellent options
PENDANTS_EXC = (13 * GROUP_SIZE + 12, 13 * GROUP_SIZE + 13)  # pendants with the weapon ones, 13/12 the magic one
LIFE_RINGS = range(13 * GROUP_SIZE + 8, 13 * GROUP_SIZE + 32)  # rings and pendants with the life recovery option

# excellent bits of armor (shields, armor, 13/8, 13/9) and of weapons (weapons, staffs, 13/12, 13/13)
EXC_LIFE, EXC_MANA, EXC_DECREASE, EXC_REFLECT, EXC_DEFENSE_RATE, EXC_ZEN = 0x20, 0x10, 0x08, 0x04, 0x02, 0x01
EXC_RATE, EXC_LEVEL, EXC_PERCENT, EXC_SPEED, EXC_LIFE_KILL, EXC_MANA_KILL = 0x20, 0x10, 0x08, 0x04, 0x02, 0x01

LUCK_CRITICAL = 5  # % per lucky weapon, the item's text. Which items count is mup's choice
EXCELLENT_RATE = 10  # % per weapon or pendant with the option
EXCELLENT_PERCENT = 4  # life, mana, damage decrease, reflect: the texts


def class_number(p):
    return p.class_type.value >> 5


def usable(item):
    """The client counts an item in hand only while it has durability."""
    return item is not None and item.durability > 0


def item_damage(item):
    """Damage min, max of a weapon with its level, excellent items more (client 0x45a270, the max's bonus uses the
    min too)."""
    i = item.info
    dmin, dmax = i.damage_min, i.damage_max
    bonus = i.damage_min * 25 // i.level + 5 if item.excellent and i.level else 0
    if i.damage_min:
        dmin += bonus + level_bonus(item.level)
    if i.damage_max:
        dmax += bonus + level_bonus(item.level)
    return dmin, dmax


def item_defense(item):
    """Defense of a worn item with its level and its option (client 0x45a270, 0x45b770)."""
    i = item.info
    defense = i.defense
    if defense:
        if item.type in SHIELDS:
            defense += item.level
        else:
            if item.excellent and i.level:
                defense += i.level // 5 + i.defense * 12 // i.level + 4
            defense += level_bonus(item.level)
    if item.type in ARMOR_TYPES:
        defense += 4 * item.option
    return defense


def item_defense_rate(item):
    """Defense rate of a shield with its level, without the option."""
    i = item.info
    rate = i.defense_rate
    if rate:
        if item.excellent and i.level:
            rate += i.defense_rate * 25 // i.level + 5
        rate += level_bonus(item.level)
    return rate


def damage_option(item):
    """Option 3C: + 4 damage per step, weapons (not ammunition) and the wings of satan."""
    if item.type < 5 * GROUP_SIZE and item.type not in (BOLT, ARROWS) or item.type == WINGS_OF_SATAN:
        return 4 * item.option
    return 0


def magic_option(item):
    """Option 3D: + 4 wizardry damage per step, staffs and the wings of heaven."""
    return 4 * item.option if item.type in STAFFS or item.type == WINGS_OF_HEAVEN else 0


def weapon_excellent(item):
    """The weapon excellent bits of an item that has them, 0 otherwise."""
    return item.excellent if item.type < SHIELDS.start or item.type in PENDANTS_EXC else 0


def armor_excellent(item):
    return item.excellent if SHIELDS.start <= item.type < ARMOR_TYPES.stop or item.type in RINGS_EXC else 0


def is_magic_item(item):
    """Staffs and 13/12 have the wizardry versions of the level / 20 and 2% options."""
    return item.type in STAFFS or item.type == PENDANTS_EXC[0]


def compute(p):
    """CombatValues of player p, the client's formulas (0x45bbd0 .. 0x45c7d0)."""
    v = CombatValues()
    inv = p.inventory
    cls = class_number(p)
    right, left, wings, pendant = inv.get(RIGHT_HAND), inv.get(LEFT_HAND), inv.get(WINGS), inv.get(PENDANT)
    level20 = p.level // 20

    # damage
    bow = usable(right) and right.type in RIGHT_BOWS or usable(left) and left.type in LEFT_BOWS
    if bow:
        base = p.agility
    elif cls == ELF:
        base = p.strength + p.agility
    else:
        base = p.strength
    hands = {RIGHT_HAND: [base // 8, base // 4], LEFT_HAND: [base // 8, base // 4]}
    if wings is not None:
        add = worn(damage_option(wings), wear_factor(wings))
        for d in hands.values():
            d[0] += add
            d[1] += add
    for slot, item in ((RIGHT_HAND, right), (LEFT_HAND, left)):
        if not usable(item):
            continue
        f = wear_factor(item)
        dmin, dmax = item_damage(item)
        d = hands[slot]
        d[0] += worn(dmin + damage_option(item), f)
        d[1] += worn(dmax + damage_option(item), f)
        exc = weapon_excellent(item)
        if not is_magic_item(item):
            if exc & EXC_LEVEL:
                d[0] += level20
                d[1] += level20
            if exc & EXC_PERCENT:
                d[0] += d[0] * 2 // 100
                d[1] += d[1] * 2 // 100
    if pendant is not None:
        exc = weapon_excellent(pendant)
        if not is_magic_item(pendant):
            for d in hands.values():
                if exc & EXC_LEVEL and usable(pendant):
                    d[0] += level20
                    d[1] += level20
                if exc & EXC_PERCENT:
                    d[0] += d[0] * 2 // 100
                    d[1] += d[1] * 2 // 100
    # levelled bolts / arrows make the other hand's bow hit harder
    if right is not None and left is not None and right.type // GROUP_SIZE == 4 and left.type // GROUP_SIZE == 4:
        for ammo, slot in ((left, RIGHT_HAND), (right, LEFT_HAND)):
            if ammo.type in (BOLT, ARROWS) and ammo.level >= 1 and (ammo is left) == (ammo.type == BOLT):
                k = (2 * ammo.level + 1) * 0.01
                hands[slot] = [d + int(d * k + 1.0) for d in hands[slot]]
    v.damage_min, v.damage_max = hands[RIGHT_HAND]
    v.left_min, v.left_max = hands[LEFT_HAND]

    # wizardry damage
    v.magic_min, v.magic_max = p.energy // 9, p.energy // 4
    if wings is not None:
        add = worn(magic_option(wings), wear_factor(wings))
        v.magic_min += add
        v.magic_max += add
    if usable(right):
        add = worn(magic_option(right), wear_factor(right))
        v.magic_min += add
        v.magic_max += add
        if is_magic_item(right) and weapon_excellent(right) & EXC_LEVEL:
            v.magic_min += level20
            v.magic_max += level20
        if right.type in STAFFS:
            rise = item_damage(right)[0] // 2 + 2 * right.level
            v.staff_rise = worn(rise, wear_factor(right, right.info.magic_durability))
    if usable(pendant) and is_magic_item(pendant):
        exc = weapon_excellent(pendant)
        if exc & EXC_LEVEL:
            v.magic_min += level20
            v.magic_max += level20
        if exc & EXC_PERCENT:
            v.magic_min += v.magic_min * 2 // 100
            v.magic_max += v.magic_max * 2 // 100

    # attack rate and speeds
    v.attack_rate = p.level * 5 + p.agility * 3 // 2 + p.strength // 4
    if cls == ELF:
        v.attack_speed = v.magic_speed = p.agility // 50
    elif cls in (DK, MG):
        v.attack_speed, v.magic_speed = p.agility // 15, p.agility // 20
    else:
        v.attack_speed = v.magic_speed = p.agility // 20
    weapons = [i for i in (right, left)
               if usable(i) and i.type not in (BOLT, ARROWS) and i.type < SHIELDS.start]
    speed = sum(i.info.attack_speed for i in weapons) // len(weapons) if weapons else 0
    gloves = inv.get(GLOVES)
    if gloves is not None:
        speed += gloves.info.attack_speed
    for item in (right, left, pendant):
        if usable(item) and weapon_excellent(item) & EXC_SPEED:
            speed += 7
    v.attack_speed += speed
    v.magic_speed += speed

    # defense rate
    v.defense_rate = p.agility // 4 if cls == ELF else p.agility // 3
    if usable(left):
        f = wear_factor(left)
        v.defense_rate += worn(item_defense_rate(left), f)
        if left.type in SHIELDS:
            v.defense_rate += worn(5 * left.option, f)
    for slot in (LEFT_HAND, HELM, ARMOR, PANTS, GLOVES, BOOTS, RING2, RING):
        item = inv.get(slot)
        if item is not None and armor_excellent(item) & EXC_DEFENSE_RATE and (slot != LEFT_HAND or usable(item)):
            v.defense_rate += v.defense_rate * 10 // 100

    # defense
    v.defense = {ELF: p.agility // 10, DK: p.agility // 3, DW: p.agility // 4, MG: p.agility // 5}[cls]
    for slot in (LEFT_HAND, HELM, ARMOR, PANTS, GLOVES, BOOTS, WINGS):
        item = inv.get(slot)
        if usable(item):
            v.defense += worn(item_defense(item), wear_factor(item))

    # what the client doesn't count
    for item in (right, left):
        if usable(item) and item.luck and item.type < SHIELDS.start:
            v.critical_rate += LUCK_CRITICAL
    for slot, item in inv.items():
        if slot > RING2 or not usable(item):
            continue
        exc = armor_excellent(item)
        v.life_bonus += EXCELLENT_PERCENT * bool(exc & EXC_LIFE)
        v.mana_bonus += EXCELLENT_PERCENT * bool(exc & EXC_MANA)
        v.damage_decrease += EXCELLENT_PERCENT * bool(exc & EXC_DECREASE)
        v.reflect += EXCELLENT_PERCENT * bool(exc & EXC_REFLECT)
        v.zen_bonus += 40 * bool(exc & EXC_ZEN)
        if item.type in LIFE_RINGS or item.type == WINGS_OF_ELF:
            v.life_recovery += item.option
        exc = weapon_excellent(item)
        v.excellent_rate += EXCELLENT_RATE * bool(exc & EXC_RATE)
        v.life_after_kill += bool(exc & EXC_LIFE_KILL)
        v.mana_after_kill += bool(exc & EXC_MANA_KILL)
    return v


def update(c, notify=True):
    """Recomputes c's player's values after a change of stats, level or equipment, life and mana stay within the
    maximum. notify: the client hears of a new maximum (26 / 27 FE), otherwise the caller's packet carries it."""
    p = c.player
    max_life, max_mana = p.max_life, p.max_mana
    p.values = compute(p)
    if p.max_life != max_life and notify:
        c.write(SLife(type=SLife.MAX, value=p.max_life))
    if p.max_mana != max_mana and notify:
        c.write(SMana(type=SMana.MAX, value=p.max_mana))
    if p.life > p.max_life:
        p.life = p.max_life
        c.write(SLife(value=p.life))
    if p.mana > p.max_mana:
        p.mana = p.max_mana
        c.write(SMana(value=p.mana))


STATS = ('strength', 'agility', 'vitality', 'energy')  # F3 06 numbers
MAX_STAT = 0xFFFF  # 2 bytes in the packets, the client checks no maximum: mup's choice


def add_point(c, stat):
    """c's player puts a level up point into stat (F3 06 number). The result tells the client, which counts on its
    own, a new maximum life (vitality) or mana (energy) with it."""
    p = c.player
    if p.dead or p.free_points <= 0 or not 0 <= stat < len(STATS) or getattr(p, STATS[stat]) >= MAX_STAT:
        c.write(SPointResult(result=0))
        return False
    setattr(p, STATS[stat], getattr(p, STATS[stat]) + 1)
    p.free_points -= 1
    update(c, notify=False)
    value = p.max_life if STATS[stat] == 'vitality' else p.max_mana if STATS[stat] == 'energy' else 0
    c.write(SPointResult(result=SPointResult.OK | stat, value=value))
    return True
