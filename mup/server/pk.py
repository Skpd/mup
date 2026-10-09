"""
Player kills, see PK in docs/protocol-097.md. Players hit each other with the client's 15 / 19 / 1D at a player's cid
(the client sends them with Ctrl held, at level 6 murderers without). The pk count makes the level the clients show
(F3 08, 12 [+30], F3 03 [40]): 0..2 heroes, 3 commoner, 4 "warning against murderers", 5 murderer, 6 the worst
(Text.bmd 487..491 for 2..6, the name colours of the client's 0x45ef10).

Killing a player who isn't a murderer and didn't attack first counts one up, killing a murderer makes a hero (one
down while not a murderer). The count goes one step back to 0 for every DECAY_TIME in game. Murderers lose an item
when they die, from level 5 shops refuse them, guards attack them and nobody parties with them. The Arena counts
nothing. The usual 0.97 rules, numbers where they aren't known are mup's.
"""
import logging
import random
from mup.model.item import GRID
from mup.packet.server import SItemDeleted, SPkLevel
from mup.server import ground, inventory, skill, stats, view

logger = logging.getLogger(__name__)

COMMONER = 3
MURDERER = 4  # from this level on a murderer: loses items on death
PUNISHED = 5  # from this level: shops refuse, guards attack, no party (usual 0.97: levels above 4)
WORST = 6
MIN_COUNT, MAX_COUNT = -3, 100  # level 0 and 6 are reached at -3 and 3, the count goes on to MAX_COUNT
MIN_LEVEL = 6  # players below it neither hit nor get hit by players, usual
ARENA = 6  # map
SELF_DEFENSE_TIME = 60.0  # seconds the attacked may hit back without it counting, mup's choice
DECAY_TIME = 1800.0  # seconds in game for one step of the count back to 0, mup's choice
DROP_CHANCE = {4: 25, 5: 50, 6: 100}  # % a murderer of the level loses an item when it dies, mup's choice


def level_of(count):
    """The pk level of a pk count: 3 + count, between 0 and 6."""
    return max(0, min(WORST, COMMONER + count))


def may_hit(game, c, target):
    """c's player may hit the player of connection target: both in game, alive and from level 6, target in view on
    the same map, neither in a safe zone, not in c's party."""
    p, t = c.player, target.player
    if target is c or t is None or not target.playing or p.dead or t.dead or target not in c.view:
        return False
    if p.level < MIN_LEVEL or t.level < MIN_LEVEL or p.map_id != t.map_id:
        return False
    if c.party is not None and c.party is target.party:
        return False
    terrain = game.maps[p.map_id].terrain
    return not terrain.safe(p.x, p.y) and not terrain.safe(t.x, t.y)


def attacked(game, c, target):
    """c's player hit the player of target: unless c is hitting back, target may now hit c without it counting, for
    SELF_DEFENSE_TIME after the last hit or until one of them dies."""
    now = game.now
    if c.self_defense.get(target, 0) > now:
        return
    target.self_defense = {o: until for o, until in target.self_defense.items() if until > now}
    target.self_defense[c] = now + SELF_DEFENSE_TIME


def killed(game, killer, victim):
    """killer's player killed the player of victim: the count of the killer changes, but in the Arena."""
    p, v = killer.player, victim.player
    if p.map_id == ARENA:
        return
    if v.pk >= MURDERER:
        if p.pk_count <= 0:
            set_count(game, killer, max(MIN_COUNT, p.pk_count - 1))
        return
    if killer.self_defense.get(victim, 0) > game.now:
        logger.info('%s killed %s in self defense', p.name, v.name)
        return
    set_count(game, killer, min(MAX_COUNT, max(0, p.pk_count) + 1))


def set_count(game, c, count):
    """c's player gets a new pk count, its time back to 0 starts again. The level shown changes with it."""
    p = c.player
    p.pk_count = count
    p.pk_time = 0.0
    level = level_of(count)
    if level != p.pk:
        logger.info('%s: pk count %s, level %s', p.name, count, level)
        p.pk = level
        show(game, c)


def show(game, c):
    """F3 08 with c's pk level to it and the players who see it."""
    packet = SPkLevel(cid=c.cid, level=c.player.pk)
    c.write(packet)
    for o in view.viewers(game, c):
        o.write(packet)


def tick(game, c, now):
    """The game tick: the time in game counts the pk count back to 0."""
    p = c.player
    elapsed = now - c.pk_clock
    c.pk_clock = now
    if p.pk_count == 0:
        return
    p.pk_time += elapsed
    if p.pk_time >= DECAY_TIME:
        set_count(game, c, p.pk_count - 1 if p.pk_count > 0 else p.pk_count + 1)


def died(game, c, rng=random):
    """c's player died: its self defense ends both ways. A murderer loses one of its items (worn or in the grid) by
    its level's chance, it falls where it lies, not in the Arena. The item, None when nothing fell."""
    c.self_defense = {}
    for o in game.playing():
        o.self_defense.pop(c, None)
    p = c.player
    if p.pk < MURDERER or p.map_id == ARENA or rng.randrange(100) >= DROP_CHANCE[p.pk]:
        return None
    slots = sorted(slot for slot in p.inventory if slot < inventory.GRID_END)
    if not slots:
        return None
    slot = rng.choice(slots)
    item = p.inventory.pop(slot)
    c.write(SItemDeleted(slot=slot, unlock=0))
    if slot < GRID:
        inventory.look_changed(game, c, slot)
        stats.update(c)
        skill.update_weapon_skills(game, c)
    logger.info('%s, a murderer, loses %s', p.name, item)
    ground.place(game, p.map_id, p.x, p.y, item=item)
    return item


def refused(c):
    """Murderers from PUNISHED on: shops and parties refuse them."""
    return c.player.pk >= PUNISHED
