"""
Using skills: on a target (19), on an area (1E, what it hits comes with the client's 1D reports), teleport (1C with
gate 0). Mana, distance and pace are checked, the damage follows the client's formulas where it shows them (Skills
and Character values in docs/protocol-097.md) and the usual 0.97 rules otherwise.
"""
import logging
import random
from dataclasses import dataclass, field
from typing import Set, Tuple
from mup.packet.server import SMagic, SMagicAOE, SMana, SLife, SMapMove, SPlace
from mup.server import combat, effect, stats, summon, view
from mup.server.world import distance

logger = logging.getLogger(__name__)

TELEPORT, TELEPORT_PARTY, MANA_SHIELD, DEFENSE, HEAL, GREATER_FORTITUDE = 6, 15, 16, 18, 26, 48
SUMMONS = range(30, 37)
BUFFS = (HEAL, effect.GREATER_DEFENSE, effect.GREATER_DAMAGE, DEFENSE, MANA_SHIELD, GREATER_FORTITUDE)
# what does no damage, the others hit with wizardry (the skill has damage) or the weapon (it hasn't)
NO_DAMAGE = {TELEPORT, TELEPORT_PARTY, *BUFFS, *SUMMONS}
LAG = 2  # tiles allowed over a skill's distance or radius, mup's choice
AREA_TIME = 3.0  # seconds an area cast takes 1D reports for its effects
TELEPORT_PAUSE = 3.0  # the client teleports at most every 3 s


@dataclass
class AreaCast:
    """An area skill cast with 1E: its 1D reports count until expires_at, each target once per effect serial."""
    skill: object
    x: int
    y: int
    expires_at: float
    hit: Set[Tuple[int, int]] = field(default_factory=set)  # (serial, cid)


def cast(game, c, index):
    """The SkillInfo of list index if c's player may use it now: it has the skill, the mana (and an arrow for a bow
    skill), and isn't too fast. Takes them. None otherwise."""
    p = c.player
    number = p.skill(index)
    info = game.skills.get(number)
    if p.dead or info is None:
        logger.debug('%s: no skill at list index %s', p.name, index)
        return None
    if p.mana < info.mana:
        logger.debug('%s has %s mana, %s needs %s', p.name, p.mana, info.name, info.mana)
        return None
    weapon = info.damage == 0 and number not in NO_DAMAGE
    ammunition = combat.ammunition(p) if weapon else None
    if ammunition is False:
        logger.debug('%s has no ammunition for %s', p.name, info.name)
        return None
    if not combat.paced(p, game.now, p.values.attack_speed if weapon else p.values.magic_speed):
        logger.info('%s casts faster than its speed allows', p.name)
        return None
    p.mana -= info.mana
    c.write(SMana(value=p.mana))
    if ammunition is not None:
        combat.use_ammunition(game, c, ammunition)
    return info


def skill_damage(p, info, rng=random):
    """Damage before defense of a damaging skill and its colour flags. Skills with damage (wizards'): wizardry +
    the skill's damage .. wizardry max + 3/2 of it (client 0x45cb20), the staff's rise on top. Without (knights',
    elves'): the weapon's damage times the skill damage the client shows, 200 + energy / 10 % for knights, / 30 for
    gladiators, the weapon's for others."""
    v = p.values
    if info.damage:
        lo, hi = v.magic_min + info.damage, v.magic_max + info.damage + info.damage // 2
        dmg, flags = combat.roll(v, [(lo, hi, 100 + v.staff_rise)], rng)
    else:
        dmg, flags = combat.roll(v, combat.weapon_ranges(p), rng)
        cls = stats.class_number(p)
        if cls == stats.DK:
            dmg = dmg * (200 + p.energy // 10) // 100
        elif cls == stats.MG:
            dmg = dmg * (200 + p.energy // 30) // 100
    return dmg, flags


def hit(game, c, target, info, rng=random):
    """A damaging skill reaches target, a monster or a player: miss check, damage less the defense, the skill's
    effect."""
    p = c.player
    if not combat.hit_check(p.values.attack_rate, combat.defense_rate_of(target), rng):
        combat.hit(c, target, 0, magic=True)
        return False
    dmg, flags = skill_damage(p, info, rng)
    dmg += effect.value(c, effect.GREATER_DAMAGE)
    combat.wear_weapon(c, target, magic=bool(info.damage))
    combat.hit(c, target, combat.damage_taken(target, dmg, p.level), flags, magic=True)
    if not combat.where(target).dead:
        if info.number == effect.POISON:
            effect.apply(game, target, effect.POISON, effect.POISON_TIME, source=c)
        elif info.number == effect.ICE:
            effect.apply(game, target, effect.ICE, effect.ICE_TIME)
    return True


def on_target(game, c, index, target_cid):
    """19: a skill on a target, the caster and the players who see it get the animation (bit 15: it took
    effect)."""
    p = c.player
    info = cast(game, c, index)
    if info is None:
        return
    player = game.connections.get(target_cid)
    applied = False
    if info.number in SUMMONS:
        applied = summon.call(game, c, info.number)
        target_cid = c.cid
    elif info.number in BUFFS:
        target = player if player is not None and player.player is not None else c
        if target is c or (target in c.view and in_reach(p, target.player, info)):
            applied = buff(game, c, target, info)
    elif info.number in NO_DAMAGE:
        logger.debug('%s: %s isn\'t used on a target', p.name, info.name)
    else:
        # a monster, or a player (mup.server.pk)
        target = combat.target_of(game, c, target_cid)
        if target is not None and in_reach(p, combat.where(target), info):
            summon.owner_attacks(c, target)
            applied = hit(game, c, target, info)
        else:
            logger.debug('%s: %s on %s out of reach or not in view', p.name, info.name, target_cid)

    animation = SMagic.of(info.number, c.cid, target_cid, applied)
    c.write(animation)
    for o in view.viewers(game, c):
        o.write(animation)


def in_reach(p, target, info):
    return distance(p.x, p.y, target.x, target.y) <= info.distance + LAG


def buff(game, c, target, info):
    """The elf's heal and greater defense / damage, the knight's defense (on itself). The strengths are the usual
    0.97 ones: heal 5 + energy / 5, defense + 2 + energy / 8, damage + 3 + energy / 7."""
    p = c.player
    t = target.player
    if t.dead:
        return False
    if info.number == HEAL:
        t.life = min(t.max_life, t.life + 5 + p.energy // 5)
        target.write(SLife(value=t.life))
    elif info.number == effect.GREATER_DEFENSE:
        effect.apply(game, target, info.number, effect.BUFF_TIME, 2 + p.energy // 8)
    elif info.number == effect.GREATER_DAMAGE:
        effect.apply(game, target, info.number, effect.BUFF_TIME, 3 + p.energy // 7)
    elif info.number == DEFENSE and target is c:
        effect.apply(game, c, DEFENSE, effect.DEFENSE_TIME)
    else:
        return False
    return True


def on_area(game, c, index, x, y, direction):
    """1E: an area skill at x, y. The animation goes out, the hits come with the client's 1D reports."""
    p = c.player
    info = cast(game, c, index)
    if info is None:
        return
    p.direction = direction & 0x07
    animation = SMagicAOE(skill=info.number, caster=c.cid, x=x, y=y)
    c.write(animation)
    for o in view.viewers(game, c):
        o.write(animation)
    if distance(p.x, p.y, x, y) > info.distance + LAG:
        logger.debug('%s: %s at %s,%s, too far from %s,%s', p.name, info.name, x, y, p.x, p.y)
        return
    c.area_casts[info.number] = AreaCast(info, x, y, game.now + AREA_TIME)


def area_hits(game, c, index, x, y, serial, cids):
    """1D: an area skill's effect landed at x, y and reached cids. Counted for a skill cast with 1E a moment ago,
    for monsters in view and players c may hit within its radius, each once per effect."""
    p = c.player
    number = p.skill(index)
    a = c.area_casts.get(number)
    if p.dead or a is None or game.now > a.expires_at:
        logger.debug('%s: 1D for skill %s without a cast', p.name, number)
        return
    radius = max(a.skill.radius, 1) + LAG
    if distance(x, y, a.x, a.y) > radius:
        logger.debug('%s: %s landed at %s,%s, far from %s,%s', p.name, a.skill.name, x, y, a.x, a.y)
        return
    for cid in cids:
        target = combat.target_of(game, c, cid)
        if p.dead:
            break
        if target is None or (serial, cid) in a.hit:
            continue
        at = combat.where(target)
        if distance(at.x, at.y, x, y) > radius:
            continue
        a.hit.add((serial, cid))
        hit(game, c, target, a.skill)


def teleport(game, c, x, y):
    """1C with gate 0: the teleport skill to x, y of the map. The client checks the tile and the pace itself."""
    p = c.player
    index = next((i for i, s in enumerate(p.skills) if s == TELEPORT), None)
    m = game.maps[p.map_id]
    if index is None or not m.terrain.walkable(x, y) or m.terrain.safe(x, y):
        logger.debug('%s can\'t teleport to %s,%s', p.name, x, y)
        return
    if game.now < c.teleport_at:
        return
    info = game.skills[TELEPORT]
    if distance(p.x, p.y, x, y) > info.distance + LAG or p.mana < info.mana:
        return
    p.mana -= info.mana
    c.write(SMana(value=p.mana))
    c.teleport_at = game.now + TELEPORT_PAUSE
    m.move_player(c, x, y)
    p.walk_path = []
    c.write(SMapMove(map_change=0, map=p.map_id, x=x, y=y, direction=p.direction))
    place = SPlace(cid=c.cid, x=x, y=y)
    for o in view.refresh(game, c):
        o.write(place)
