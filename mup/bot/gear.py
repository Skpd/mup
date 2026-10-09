"""
A bot's items: what a piece is worth to it, what it wears, keeps, picks up and drops. From what its client shows:
its inventory (its own Player.inventory, which the server's answers keep the client's in step with), the items on
the ground in its view (their 4 item bytes) and the game's data.

A piece of equipment is worth what its character window would show with the piece worn against without
(mup.server.stats, the client's formulas) put through the career's fights against the monsters it hunts
(mup.bot.career): the share of exp per second it adds, the raw values (damage, defense, speeds) breaking ties. A
piece at 0 durability gives nothing, a bow nothing without its arrows. One it can wear within a few levels counts
part of its gain, the level up points go to it first (goal). Other items are worth what they do for it: potions
while it carries few, the scrolls and orbs of skills it can learn, jewels (kept for trading in B2). The rest is
junk, left on the ground and dropped when room is needed. The weights are mup's choices.
"""
import dataclasses
from dataclasses import dataclass
from typing import Optional, Tuple
from mup.bot import career
from mup.model.item import ARROWS, BOLT, GRID, LEFT_HAND, RIGHT_HAND, RING, RING2, Item
from mup.server import combat, inventory, item as items, shop, skill, stats
from mup.server.inventory import AMMO

POTION = 0.2  # a potion while it carries fewer than KEEP of the kind
KEEP = 4  # potions of a kind (healing, mana) it carries, each takes a slot: they don't stack (M5)
SKILL = 1.0  # a scroll or orb of a skill it can learn
JEWEL = 0.5
UPGRADE = 0.01  # the least a piece it would wear counts
FUTURE = 0.5  # share of the gain of a piece it can wear within AHEAD levels
AHEAD = 3  # levels
TIE = 0.01  # weight of the raw values' change when the exp per second doesn't change
SAME = 1e-9  # share of the exp per second a change has to make to count
JEWELS = (shop.JEWEL_OF_BLESS, shop.JEWEL_OF_SOUL, shop.JEWEL_OF_LIFE, shop.JEWEL_OF_CHAOS)
HEALING, MANA = 'healing', 'mana'


def potion_kind(item):
    """HEALING, MANA or None."""
    if item.type in items.HEALING:
        return HEALING
    if item.type in items.MANA:
        return MANA
    return None


def potions(p, kind):
    """Potions of kind in p's player's grid, (slot, Item) by slot."""
    return [(slot, i) for slot, i in sorted(p.inventory.items()) if slot >= GRID and potion_kind(i) == kind]


def heal(p, item):
    """Life a healing potion gives p's player (mup.server.inventory.use)."""
    return max(0, item.info.value * 10 - p.level * 2) + p.max_life * items.HEALING[item.type] // 100


def potion_for(p, kind):
    """The grid slot of the potion of kind it drinks: the healing potion that gives most without going over the
    life it lacks, else the one that gives least; the first mana potion. None without one."""
    found = potions(p, kind)
    if not found:
        return None
    if kind == MANA:
        return found[0][0]
    lacks = p.max_life - p.life
    under = [(heal(p, i), slot) for slot, i in found if heal(p, i) <= lacks]
    if under:
        return max(under, key=lambda h: (h[0], -h[1]))[1]
    return min((heal(p, i), slot) for slot, i in found)[1]


def uses_mana(game, p):
    """p's player knows a skill that takes mana."""
    return any(n is not None and n in game.skills and game.skills[n].mana > 0 for n in p.skills)


def trial(game, p, inv):
    """A copy of p's player with the inventory inv, its values and weapon skills as the server would make them
    (mup.server.stats.update, mup.server.skill.update_weapon_skills)."""
    q = dataclasses.replace(p, inventory=inv)
    granted = []
    for slot in skill.HANDS:
        item = inv.get(slot)
        number = skill.weapon_skill(item) if item is not None else None
        if number in game.skills and skill.may_use(q, game.skills[number]):
            granted.append(number)
    q.skills = [s for s in p.skills if s not in skill.WEAPON_SKILLS] + granted
    q.values = stats.compute(q)
    return q


def power(game, p, types, risk=0.5):
    """(exp per second, raw values) of p's player hunting the monster types: the mean over them of the exp of a
    kill per second of fighting and resting after it (mup.bot.career.fight), nothing for those it can't kill; the
    raw values are the damage of its hits (the hands it hits with), wizardry, defense, defense rate and speeds."""
    rates = []
    if types and combat.ammunition(p) is not False:
        fights = career.fights_for(game, p, types, risk)
        regen = career.regen_rate(p)
        for t in sorted(types):
            f = fights[t]
            if f.ok:
                rates.append(f.exp / (f.kill_time + max(0.0, f.damage - regen * f.kill_time) / regen))
            else:
                rates.append(0.0)
    v = p.values
    hits = sum((lo + hi) / 2 * share / 100 for lo, hi, share in combat.weapon_ranges(p))
    raw = hits + (v.magic_min + v.magic_max) / 2 + v.defense + v.defense_rate / 4 + (v.attack_speed + v.magic_speed) / 2
    return (sum(rates) / len(rates) if rates else 0.0), raw


def gain(before, after):
    """The share a change of power from before to after adds: of the exp per second, of the raw values (times
    TIE) when that doesn't change. A consistent order, so changes can't go round in circles."""
    (r0, w0), (r1, w1) = before, after
    if abs(r1 - r0) > SAME * max(r0, r1):
        return (r1 - r0) / r0 if r0 > 0 else 1.0
    return TIE * (w1 - w0) / max(w0, 1.0)


def slots_for(item):
    """Equipment slots an item may go in by its type: its slot class, either ring slot, also the left hand for a
    one-handed weapon (the client's rule, docs/protocol-097.md, Items)."""
    wanted = items.slot_class(item.type)
    if wanted is None:
        return ()
    if wanted == RING:
        return RING, RING2
    if wanted == RIGHT_HAND and item.info.width == 1 and item.type not in AMMO:
        return RIGHT_HAND, LEFT_HAND
    return wanted,


def clash(a, b):
    """Items a and b may not share the hands: a two-handed weapon with anything but ammunition."""
    return a.info.two_handed and b.type not in AMMO or b.info.two_handed and a.type not in AMMO


@dataclass
class Change:
    """Pieces into equipment slots: what has to leave the slots first, then the pieces in order (the arrows before
    their bow), the share it adds."""
    out: Tuple[int, ...]  # equipment slots emptied first
    wear: Tuple[Tuple[Optional[int], int, Item], ...]  # (grid slot, None: on the ground; equipment slot; item)
    after: dict  # the inventory then
    gain: float

    @property
    def item(self):
        """The piece it is about, None when only a bow without its arrows comes off."""
        return self.wear[-1][2] if self.wear else None


def ammunition_for(item):
    """(ammunition type, the hand it goes in) a bow or crossbow shoots, None for other items."""
    if item.type in stats.LEFT_BOWS:
        return ARROWS, RIGHT_HAND
    if item.type in stats.RIGHT_BOWS:
        return BOLT, LEFT_HAND
    return None


def change_for(p, item, slot, source=None):
    """(inventory after, slots emptied first, pieces worn) when item goes into equipment slot from grid slot source
    (None: from the ground), with the ammunition of the grid a bow needs; None when it may not by the client's rules
    and the requirements (mup.server.inventory.can_wear)."""
    inv = dict(p.inventory)
    if source is not None:
        del inv[source]
    out = [slot] if slot in inv else []
    if slot in (RIGHT_HAND, LEFT_HAND):
        other = LEFT_HAND if slot == RIGHT_HAND else RIGHT_HAND
        if other in inv and clash(item, inv[other]):
            out.append(other)
    for s in out:
        del inv[s]
    wear = []
    ammo = ammunition_for(item)
    if ammo is not None and (ammo[1] not in inv or inv[ammo[1]].type != ammo[0]):
        stack = next(((s, i) for s, i in sorted(inv.items()) if s >= GRID and i.type == ammo[0]), None)
        if stack is not None:
            if ammo[1] in inv:
                out.append(ammo[1])
                del inv[ammo[1]]
            del inv[stack[0]]
            inv[ammo[1]] = stack[1]
            wear.append((stack[0], ammo[1], stack[1]))
    if not inventory.can_wear(dataclasses.replace(p, inventory=inv), item, slot):
        return None
    inv[slot] = item
    wear.append((source, slot, item))
    return inv, tuple(out), tuple(wear)


def best_change(game, p, types, risk=0.5, item=None, source=None):
    """The Change of the most gain: item (from grid slot source, None: from the ground) or, without an item, any
    piece of the grid, or a bow without arrows taken off. None when nothing makes it better."""
    now = power(game, p, types, risk)
    if item is None and combat.ammunition(p) is False:
        bow = LEFT_HAND if LEFT_HAND in p.inventory and p.inventory[LEFT_HAND].type in stats.LEFT_BOWS else RIGHT_HAND
        after = {s: i for s, i in p.inventory.items() if s != bow}
        return Change((bow,), (), after, gain(now, power(game, trial(game, p, after), types, risk)))
    candidates = [(source, item)] if item is not None else [
        (slot, i) for slot, i in sorted(p.inventory.items()) if slot >= GRID]
    best = None
    for src, i in candidates:
        for slot in slots_for(i):
            c = change_for(p, i, slot, src)
            if c is None:
                continue
            after, out, wear = c
            g = gain(now, power(game, trial(game, p, after), types, risk))
            if g > 0 and (best is None or g > best.gain):
                best = Change(out, wear, after, g)
    return best


def raised(p, item):
    """p's player at the level and stats item asks for (the points spent on it, AHEAD levels at most), None when it
    can't get there that soon or its class may never wear it."""
    if not inventory.class_allowed(p, item.info):
        return None
    r = items.requirements(item)
    missing = sum(max(0, need - have) for need, have in ((r.strength, p.strength), (r.agility, p.agility),
                                                          (r.energy, p.energy)))
    levels = max(0, r.level - p.level)
    if levels > AHEAD or missing > p.free_points + AHEAD * p.class_info.level_points:
        return None
    return dataclasses.replace(p, level=max(p.level, r.level), strength=max(p.strength, r.strength),
                               agility=max(p.agility, r.agility), energy=max(p.energy, r.energy))


def learnable(game, p, item, ahead=False):
    """item is a scroll or orb of a skill p's player doesn't know and may learn: now (the server's rule,
    mup.server.inventory.learn), or with ahead within AHEAD levels."""
    number = skill.taught_by(item)
    if number is None or number not in game.skills or number in p.skills:
        return False
    if not inventory.class_allowed(p, item.info):
        return False
    r = items.requirements(item)
    if p.level >= r.level and p.strength >= r.strength and p.agility >= r.agility and p.energy >= r.energy:
        return True
    return ahead and raised(p, item) is not None


def value(game, p, item, types, risk=0.5, source=None):
    """
    What item is worth to p's player, 0 for junk: a piece it would wear the share it adds (at least UPGRADE), one it
    can wear within AHEAD levels FUTURE of that; potions while it has fewer than KEEP of the kind (mana potions when
    a skill takes mana); a scroll or orb it can learn; jewels. source: the item's grid slot, None on the ground.
    """
    kind = potion_kind(item)
    if kind is not None:
        if kind == MANA and not uses_mana(game, p):
            return 0.0
        have = sum(i.durability for slot, i in potions(p, kind) if slot != source)
        return POTION if have < KEEP else 0.0
    if skill.taught_by(item) is not None:
        return SKILL if learnable(game, p, item, ahead=True) else 0.0
    if item.type in JEWELS:
        return JEWEL
    if item.type in AMMO:
        return POTION if inventory.class_allowed(p, item.info) else 0.0
    if not slots_for(item) or not inventory.class_allowed(p, item.info):
        return 0.0
    c = best_change(game, p, types, risk, item, source)
    if c is not None:
        return max(c.gain, UPGRADE)
    q = raised(p, item)
    if q is None:
        return 0.0
    q = trial(game, q, q.inventory)
    c = best_change(game, q, types, risk, item, source)
    return FUTURE * max(c.gain, UPGRADE) if c is not None else 0.0


def goal(game, p, types, risk=0.5):
    """(strength, agility, vitality, energy) the most worth piece, scroll or orb of its grid asks for that p's
    player can't use yet but can within AHEAD levels: where its next level up points go (mup.bot.career.next_point).
    None without one."""
    best = None
    for slot, item in sorted(p.inventory.items()):
        if slot < GRID:
            continue
        if skill.taught_by(item) is not None:
            if learnable(game, p, item) or not learnable(game, p, item, ahead=True):
                continue
            worth = SKILL
        else:
            if not slots_for(item) or raised(p, item) is None or best_change(game, p, types, risk, item, slot):
                continue
            worth = value(game, p, item, types, risk, slot)
        if worth > 0 and (best is None or worth > best[0]):
            best = worth, item
    if best is None:
        return None
    r = items.requirements(best[1])
    return r.strength, r.agility, 0, r.energy
