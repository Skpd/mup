"""
Item types from the client's item.bmd and the server's Item.txt, and what the client computes per item: where it
is worn and its requirements. Layouts and formulas in Items, docs/protocol-097.md.
"""
import shlex
from collections import namedtuple
from mup.model.item import (GROUP_SIZE, BOLT, ARROWS, ItemInfo, RIGHT_HAND, LEFT_HAND, HELM, WINGS, PET, PENDANT,
                            RING)

BMD_RECORD = 56
BMD_COUNT = 512
BMD_KEY = b'\xFC\xCF\xAB'

SUMMON_ORB = 12 * GROUP_SIZE + 11
RING_OF_TRANSFORM = 13 * GROUP_SIZE + 10

Requirements = namedtuple('Requirements', 'level strength agility energy')

# healing: life + value * 10 - level * 2 + this % of the maximum, mana potions: this % of the maximum. The usual values
# of the later WebZen servers, the value is item.bmd's
HEALING = {14 * GROUP_SIZE + 0: 10, 14 * GROUP_SIZE + 1: 20, 14 * GROUP_SIZE + 2: 30, 14 * GROUP_SIZE + 3: 40}
MANA = {14 * GROUP_SIZE + 4: 20, 14 * GROUP_SIZE + 5: 30, 14 * GROUP_SIZE + 6: 40}


def load_info(bmd_path, txt_path=None):
    """Item type -> ItemInfo, from the client's item.bmd and the server's Item.txt (skill, options, drops)."""
    data = open(bmd_path, 'rb').read()
    if len(data) < BMD_RECORD * BMD_COUNT:
        raise ValueError('{}: {} bytes, too short for {} items'.format(bmd_path, len(data), BMD_COUNT))
    server = _load_txt(txt_path) if txt_path else {}

    info = {}
    for n in range(BMD_COUNT):
        r = bytes(b ^ BMD_KEY[i % 3] for i, b in enumerate(data[n * BMD_RECORD:(n + 1) * BMD_RECORD]))
        name = r[:30].split(b'\0', 1)[0]
        if not name:
            continue
        skill, options, drops = server.get(n, (False, False, False))
        info[n] = ItemInfo(
            type=n, name=name.decode('cp949', errors='replace'), two_handed=bool(r[30]), level=r[31],
            width=r[32], height=r[33], damage_min=r[34], damage_max=r[35], defense_rate=r[36], defense=r[37],
            magic_defense=r[38], attack_speed=r[39], walk_speed=r[40], durability=r[41], magic_durability=r[42],
            strength=r[43], agility=r[44], energy=r[45], level_required=r[46], value=r[47],
            classes=tuple(r[48:52]), resistances=tuple(r[52:56]), skill=skill, options=options, drops=drops)
    return info


def _load_txt(path):
    """Item type -> (skill, options, drops) of a later server's Item.txt, the types this client has (index < 32)."""
    values = {}
    group = None
    with open(path, encoding='latin-1') as f:
        for line in f:
            v = shlex.split(line.split('//', 1)[0])
            if not v:
                continue
            if v[0] == 'end':
                group = None
            elif group is None:
                group = int(v[0])
            elif int(v[0]) < GROUP_SIZE:
                # Index Slot Skill Width Height HaveSerial HaveOption DropItem Name ...
                values[group * GROUP_SIZE + int(v[0])] = (v[2] != '0', v[6] != '0', v[7] != '0')
    return values


def slot_class(t):
    """The equipment slot an item type goes in, None when it can't be worn (client 0x45a270)."""
    group, index = divmod(t, GROUP_SIZE)
    if group <= 5:
        return LEFT_HAND if group == 4 and (index <= 7 or index == 17) else RIGHT_HAND
    if group == 6:
        return LEFT_HAND
    if group <= 11:
        return HELM + group - 7
    if group == 12:
        return WINGS if index <= 6 else None
    if group == 13:
        if index <= 7:
            return PET
        return RING if index <= 11 else PENDANT
    return None


def requirements(item):
    """Level, strength, agility and energy the client asks for an item (0x45a270)."""
    i = item.info
    base = i.level + (25 if item.excellent else 0) + 3 * item.level

    def stat(value, factor, divisor):
        return value and base * value * factor // divisor + 20

    strength = stat(i.strength, 3, 100)
    if strength and item.type < 12 * GROUP_SIZE and item.type not in (BOLT, ARROWS):
        strength += 5 * item.option
    if item.type == SUMMON_ORB:
        energy = (30, 60, 90, 130, 170, 210)[item.level] if item.level < 6 else 300
    else:
        energy = stat(i.energy, 4, 10)
    if item.type == RING_OF_TRANSFORM:
        level = 20 if item.level < 3 else 50
    else:
        level = i.level_required and i.level_required + 4 * item.level
    if level and item.excellent:
        level += 20
    return Requirements(level, strength, stat(i.agility, 3, 100), energy)
