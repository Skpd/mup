"""
Skills: the client's skill.bmd (the record index is the skill number) with the later server's Skill.txt for what the
client doesn't have (area radius, effect, classes), the skill list of a player and learning from scrolls and orbs.
Layouts in Skills, docs/protocol-097.md.
"""
import logging
import shlex
from mup.model.item import GROUP_SIZE, BOLT, ARROWS
from mup.model.skill import SkillInfo
from mup.packet.server import SSkillChange

logger = logging.getLogger(__name__)

BMD_RECORD = 38
BMD_COUNT = 64
BMD_KEY = b'\xFC\xCF\xAB'  # restarts at every record
MAX_SKILLS = 20  # slots of the client's list (F3 11)

SCROLLS = 15 * GROUP_SIZE  # scroll 15/n teaches skill n + 1
SCROLL_COUNT = 14
SUMMON_ORB = 12 * GROUP_SIZE + 11  # teaches 30 + its level
SUMMON = 30
ORBS = {12 * GROUP_SIZE + 7: 41, 12 * GROUP_SIZE + 8: 26, 12 * GROUP_SIZE + 9: 27, 12 * GROUP_SIZE + 10: 28}


def load(bmd_path, txt_path=None):
    """Skill number -> SkillInfo, from the client's skill.bmd and the server's Skill.txt (radius, effect, classes)."""
    data = open(bmd_path, 'rb').read()
    if len(data) < BMD_RECORD * BMD_COUNT:
        raise ValueError('{}: {} bytes, too short for {} skills'.format(bmd_path, len(data), BMD_COUNT))
    server = _load_txt(txt_path) if txt_path else {}

    skills = {}
    for n in range(BMD_COUNT):
        r = bytes(b ^ BMD_KEY[i % 3] for i, b in enumerate(data[n * BMD_RECORD:(n + 1) * BMD_RECORD]))
        name = r[:32].split(b'\0', 1)[0]
        if not name:
            continue
        skills[n] = SkillInfo(number=n, name=name.decode('cp949', errors='replace'), level=r[32], damage=r[33],
                              mana=r[34] | r[35] << 8, distance=r[36], **server.get(n, {}))
    return skills


def _load_txt(path):
    """Skill number -> radius, effect and classes of a later server's Skill.txt."""
    values = {}
    with open(path, encoding='latin-1') as f:
        for line in f:
            v = shlex.split(line.split('//', 1)[0])
            if not v or v[0] == 'end':
                continue
            # Index Name Damage MP BP Range Radio Delay Type Effect ReqLevel ReqEnergy ReqLeadership ReqKillCount
            # ReqGuildStatus DW DK FE MG DL
            values[int(v[0])] = {'radius': int(v[6]), 'effect': int(v[9]),
                                 'classes': tuple(int(x) for x in v[15:19])}
    return values


def taught_by(item):
    """The skill number an item teaches, None for other items."""
    if SCROLLS <= item.type < SCROLLS + SCROLL_COUNT:
        return item.type - SCROLLS + 1
    if item.type == SUMMON_ORB:
        return SUMMON + item.level if item.level <= 6 else None
    return ORBS.get(item.type)


def learn(c, number, notify=True):
    """c's player learns skill number into the first free slot of its list, F3 11 FE tells the client. False when
    it has it or the list is full."""
    skills = c.player.skills
    if number in skills:
        return False
    slot = next((i for i, s in enumerate(skills) if s is None), len(skills))
    if slot >= MAX_SKILLS:
        return False
    if slot == len(skills):
        skills.append(number)
    else:
        skills[slot] = number
    logger.info('%s learned skill %s in slot %s', c.player.name, number, slot)
    if notify:
        c.write(SSkillChange(change=SSkillChange.ADD, slot=slot, skill=number))
    return True


def forget(c, number, notify=True):
    """c's player loses skill number, its slot is left empty (F3 11 FF). False when it doesn't have it."""
    skills = c.player.skills
    if number not in skills:
        return False
    slot = skills.index(number)
    skills[slot] = None
    while skills and skills[-1] is None:
        skills.pop()
    if notify:
        c.write(SSkillChange(change=SSkillChange.REMOVE, slot=slot))
    return True


# the skill of a weapon or shield with the skill bit, by type, when the item's class byte allows a knight (client
# 0x45a270): 18 defense, 19 falling slash, 20 lunge, 21 uppercut, 22 cyclone, 23 slash
KNIGHT_WEAPON_SKILLS = {
    **{t: 18 for t in range(6 * GROUP_SIZE + 4, 7 * GROUP_SIZE)},
    **{t: 21 for t in (4, 7, 8)},
    **{t: 20 for t in (3, 6, 9, 11, 17, 3 * GROUP_SIZE + 4)},
    **{t: 22 for t in (5, 10, 13, 14, 16, 3 * GROUP_SIZE, 3 * GROUP_SIZE + 7, 3 * GROUP_SIZE + 8, 3 * GROUP_SIZE + 9)},
    **{t: 19 for t in (12, *range(GROUP_SIZE + 2, 2 * GROUP_SIZE), 2 * GROUP_SIZE + 1, 2 * GROUP_SIZE + 3,
                       2 * GROUP_SIZE + 4)},
    **{t: 23 for t in (15, 2 * GROUP_SIZE + 5, 2 * GROUP_SIZE + 6)},
}
TRIPLE_SHOT = 24  # elf bows and crossbows
SLASH = 23  # also 0/18 for gladiators
WEAPON_SKILLS = range(18, 25)
HANDS = (0, 1)


def weapon_skill(item):
    """The skill a weapon or shield gives while worn, None when it has none."""
    if not item.skill:
        return None
    classes = item.info.classes
    if classes[1] and item.type in KNIGHT_WEAPON_SKILLS:
        return KNIGHT_WEAPON_SKILLS[item.type]
    if classes[2] and 4 * GROUP_SIZE <= item.type < 5 * GROUP_SIZE and item.type not in (BOLT, ARROWS):
        return TRIPLE_SHOT
    if classes[3] and item.type == 18:
        return SLASH
    return None


def may_use(p, info):
    """The skill's class column (Skill.txt) allows p's class: 1 yes, 2 second classes only."""
    allowed = info.classes[p.class_type.value >> 5]
    return allowed == 1 or allowed == 2 and bool(p.class_type.value & 0x10)


def update_weapon_skills(game, c, notify=True):
    """c's player has the skills of the weapons in its hands, those of weapons it put away are gone."""
    p = c.player
    granted = set()
    for slot in HANDS:
        item = p.inventory.get(slot)
        number = weapon_skill(item) if item is not None else None
        if number in game.skills and may_use(p, game.skills[number]):
            granted.add(number)
    for number in WEAPON_SKILLS:
        if number in granted:
            learn(c, number, notify)
        else:
            forget(c, number, notify)
