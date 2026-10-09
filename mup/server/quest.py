"""
The second class quests of priest Sevina (NPC 235), on the client's quest window (Quest window in
docs/protocol-097.md). The client's Quest.bmd says what each quest wants (an item for the class, a level, zen) and
which dialog to show for each state, the server keeps the states (A0, A1, A2) and gives the rewards (A3).

States, 2 bits per quest: 3 not started, 1 accepted, 2 done. Talking to Sevina opens the window on the first quest
of the class that isn't done. Proceeding (A2) on a quest not started takes its zen and accepts it, on an accepted
one takes its item and finishes it. The quests are done in order, the rewards are the usual ones (a later server's
QuestReward.txt): 10 level up points for quest 0, 10 points and the second class for quest 1. A quest's item drops
only for a player who accepted it, from the usual monster levels.
"""
import logging
import random
import struct
from dataclasses import dataclass
from typing import Tuple
from mup.model.item import GROUP_SIZE
from mup.model.player import CharacterClass
from mup.packet.server import SItemDeleted, SPickUpResult, SQuestDialog, SQuestResult, SQuestReward, SQuestStates
from mup.server import inventory, stats, view

logger = logging.getLogger(__name__)

NPC = 235  # priest Sevina
WINDOW = 'quest'  # mup.server.npc.Window kind while the quest window is open
NOT_STARTED, ACCEPTED, DONE = 3, 1, 2
STATE_BYTES = 50  # the client keeps 50
ALL = 0xFF  # a requirement for every condition group
SECOND_CLASS = 0x10  # bit of CharacterClass
# rewards by quest: level up points, second class. Usual, a later server's QuestReward.txt
POINTS = {0: 10, 1: 10}
CLASS_CHANGE = {1}
# monster levels whose kills may drop the item of an accepted quest, and the chance (times the drop rate). Usual, a
# later server's QuestObjective.txt
DROP_LEVELS = {0: range(45, 61), 1: range(62, 77)}
DROP_CHANCE = 0.01

RECORD, CONDITIONS, REQUIREMENTS = 584, 16, 16
KEY = b'\xFC\xCF\xAB'


@dataclass(frozen=True)
class Condition:
    """What a quest wants from the classes it applies to: count items of a type."""
    item: int
    count: int
    group: int  # matched by the requirements' groups
    classes: Tuple[int, int, int, int]  # dark wizard, dark knight, elf, magic gladiator: 0 no, 1 first, 2 second


@dataclass(frozen=True)
class Requirement:
    group: int  # condition group it applies to, ALL: every one
    min_level: int  # 0: none
    max_level: int
    zen: int


@dataclass(frozen=True)
class Quest:
    index: int
    name: str
    conditions: Tuple[Condition, ...]
    requirements: Tuple[Requirement, ...]


def load(path):
    """Quest index -> Quest of the client's Quest.bmd: 200 records of 584 bytes, each xored with FC CF AB on its
    own."""
    with open(path, 'rb') as f:
        data = f.read()
    quests = {}
    for index in range(len(data) // RECORD):
        r = bytes(b ^ KEY[i % 3] for i, b in enumerate(data[index * RECORD:(index + 1) * RECORD]))
        conditions, requirements = struct.unpack_from('<HH', r)
        if not conditions:
            continue
        name = r[6:38].split(b'\0', 1)[0].decode('euc-kr', 'replace')  # some are Korean
        found = []
        for n in range(min(conditions, CONDITIONS)):
            c = r[38 + n * 18:38 + (n + 1) * 18]
            if c[1] == 1:  # bring an item, the only kind the client knows
                found.append(Condition(c[2] * GROUP_SIZE + c[3], c[4], c[5], tuple(c[6:10])))
        needed = []
        for n in range(min(requirements, REQUIREMENTS)):
            group, = struct.unpack_from('<B', r, 328 + n * 16 + 1)
            low, high, zen = struct.unpack_from('<HHI', r, 328 + n * 16 + 4)
            needed.append(Requirement(group, low, high, zen))
        quests[index] = Quest(index, name, tuple(found), tuple(needed))
    return quests


def position(index):
    """Byte and shift of a quest's state bits where the client reads them (0x4016d0, a bug): byte index >> 2, shift
    2 * (index - index >> 2) as the CPU masks it. None for the indices whose state the client can't read."""
    shift = 2 * ((index - (index >> 2)) & 15)
    return (index >> 2, shift) if shift < 8 else None


def states(p):
    """The STATE_BYTES state bytes of p, a new character has every quest not started."""
    s = bytearray(p.quest_state[:STATE_BYTES])
    return s + b'\xFF' * (STATE_BYTES - len(s))


def state(p, index):
    byte, shift = position(index)
    return states(p)[byte] >> shift & 3


def set_state(p, index, value):
    s = states(p)
    byte, shift = position(index)
    s[byte] = s[byte] & ~(3 << shift) & 0xFF | value << shift
    p.quest_state = bytes(s)


def condition(q, p):
    """The condition of quest q for p's class: its class byte 1 (the only one the client shows texts for), or 2 for a
    second class. None when the quest isn't for the class."""
    number = p.class_type.value >> 5
    allowed = (1, 2) if p.class_type.value & SECOND_CLASS else (1,)
    return next((c for c in q.conditions if c.classes[number] in allowed), None)


def requirements(q, cond):
    return [r for r in q.requirements if r.group in (ALL, cond.group)]


def current(game, p):
    """The quest Sevina talks about with p: the first one of its class not done, else the last one of its class.
    None when no quest is for its class."""
    mine = [q for i, q in sorted(game.quests.items()) if condition(q, p) is not None and position(i) is not None]
    return next((q for q in mine if state(p, q.index) != DONE), mine[-1] if mine else None)


def send_states(c):
    """A0: the states, the client takes the quest class from the hero's class with them."""
    c.write(SQuestStates.of(states(c.player)))


def talk(game, c):
    """c's player talks to Sevina: the quest window (A1) on the current quest."""
    q = current(game, c.player)
    if q is None:
        return False
    show(c, q.index)
    return True


def show(c, index):
    """A1: the quest window with the text of quest index's state."""
    c.write(SQuestDialog(quest=index, states=states(c.player)[index >> 2]))


def proceed(game, c, index):
    """
    A2: c's player goes on with quest index in Sevina's window. Not started: the level and the zen are checked, the
    zen taken, the quest accepted. Accepted: its items are taken, it is done with its rewards. The answer (A2) shows
    the new state's text, a refusal shows the window again on the quest it should be (A1).
    """
    p = c.player
    w = c.window
    if p.dead or w is None or w.kind != WINDOW:
        logger.debug('%s: A2 without the quest window', p.name)
        return False
    q = current(game, p)
    if q is None or q.index != index:
        logger.debug('%s: quest %s isn\'t the current one', p.name, index)
        if q is not None:
            show(c, q.index)
        return False
    cond = condition(q, p)
    now = state(p, index)
    if now == NOT_STARTED:
        needed = requirements(q, cond)
        zen = sum(r.zen for r in needed)
        if any(r.min_level and p.level < r.min_level or r.max_level and p.level > r.max_level for r in needed) \
                or p.zen < zen:
            logger.debug('%s doesn\'t meet the requirements of quest %s', p.name, index)
            show(c, index)
            return False
        p.zen -= zen
        c.write(SPickUpResult.zen(p.zen))
        set_state(p, index, ACCEPTED)
        logger.info('%s accepts quest %s %s for %s zen', p.name, index, q.name, zen)
    elif now == ACCEPTED:
        slots = sorted(slot for slot, item in p.inventory.items() if slot in inventory.INVENTORY
                       and item.type == cond.item)
        if len(slots) < cond.count:
            logger.debug('%s hasn\'t the items of quest %s', p.name, index)
            show(c, index)
            return False
        for slot in slots[:cond.count]:
            del p.inventory[slot]
            c.write(SItemDeleted(slot=slot, unlock=0))
        set_state(p, index, DONE)
        logger.info('%s finishes quest %s %s', p.name, index, q.name)
    else:
        show(c, index)
        return False
    c.write(SQuestResult(quest=index, states=states(p)[index >> 2]))
    if state(p, index) == DONE:
        reward(game, c, index)
    game.save(c)
    return True


def reward(game, c, index):
    """The rewards of a quest done: level up points, the second class. Everyone who sees c's player sees the
    effect."""
    p = c.player
    points = POINTS.get(index, 0)
    if points:
        p.free_points += points
        announce(game, c, SQuestReward(cid=c.cid, type=SQuestReward.POINTS, value=points))
    if index in CLASS_CHANGE and not p.class_type.value & SECOND_CLASS:
        p.class_type = CharacterClass(p.class_type.value | SECOND_CLASS)
        logger.info('%s is a %s now', p.name, p.class_type.name.lower().replace('_', ' '))
        stats.update(c)
        announce(game, c, SQuestReward(cid=c.cid, type=SQuestReward.CLASS, value=p.class_type.value))
        send_states(c)  # the client's quest class follows the hero's class only with A0


def announce(game, c, packet):
    c.write(packet)
    for o in view.viewers(game, c):
        o.write(packet)


def loot(game, mob, c, rng=random):
    """Items mob drops for c's player besides its loot: the item of its accepted quest, from the usual monster
    levels, while it hasn't enough of them."""
    p = c.player
    if p is None:
        return []
    q = current(game, p)
    if q is None or state(p, q.index) != ACCEPTED or mob.info.level not in DROP_LEVELS.get(q.index, ()):
        return []
    cond = condition(q, p)
    info = game.item_info.get(cond.item)
    have = sum(1 for item in p.inventory.values() if item.type == cond.item)
    if info is None or have >= cond.count or rng.random() >= DROP_CHANCE * game.config.drop_rate:
        return []
    return [game.new_item(info)]
