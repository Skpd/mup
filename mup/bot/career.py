"""
A bot's career: where to hunt and how to spend its level up points. From what a player knows: the game's data (the
monster and spawn files, the gates) and its own character's values (the client's formulas, mup.server.stats).

Hunting grounds are the spawns laid on CELL x CELL tile cells per map: area spawns spread over their tiles, single
ones over their few. A ground's worth to a bot is the exp per second it would make there, counting half of the cells
around: per kill the monster's exp, the time its swings or casts take and the walk to the next monster, the life
the monsters that look for players take (rested back at the regeneration's pace), no more kills than the respawns
allow. A ground with a monster that looks and would kill it in one fight is left out (a deadly cell: the bot doesn't
walk through it either), so is one that only has monsters it can't kill in time. The walk there is taken off over a
horizon of hunting.
"""
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from mup.bot import motor
from mup.model.player import CharacterClass, DEFAULT_SKILLS, Player
from mup.server import combat, experience, gate, stats

CELL_BITS = 4  # cells of 16 x 16 tiles
CELL = 1 << CELL_BITS
NEIGHBOURS = 0.5  # weight of the monsters of the 8 cells around
MIN_MONSTERS = 0.5  # a ground has at least this many around: a single spawn spread over two cells counts
DEADLY = 0.5  # monsters of a type that would kill the bot around a cell (its own and half of the next) that make it
# a deadly one
MAX_KILL_TIME = 60.0  # seconds a kill may take
FIGHT_LIMIT = 30.0  # seconds of a fight that may go on before the bot would leave
DEADLY_LIFE = 0.8  # share of its life a fight with a monster that looks takes that makes the monster deadly
HORIZON = 300.0  # seconds it would hunt on a ground before it looks again, the walk there is weighed against it
VARIETY = 0.05  # a bot's liking of a ground varies by this share, so bots of a class spread a little

# shares of the level up points by class (strength, agility, vitality, energy), mup's choice: knights and gladiators
# hit harder and last, wizards cast, elves fight with what strength and agility give before they have a bow
BUILDS = {
    CharacterClass.DARK_KNIGHT: (5, 2, 3, 0),
    CharacterClass.DARK_WIZARD: (1, 2, 2, 5),
    CharacterClass.ELF: (3, 4, 2, 1),
    CharacterClass.MAGIC_GLADIATOR: (4, 2, 2, 2),
}


@dataclass
class Ground:
    """A cell of a map with the monsters expected in it by type."""
    map_id: int
    cell: Tuple[int, int]
    tiles: List[Tuple[int, int]]  # walkable tiles outside the safe zone
    counts: Dict[int, float] = field(default_factory=dict)  # monster type -> monsters
    _center: Tuple[int, int] = None

    @property
    def key(self):
        return self.map_id, self.cell[0], self.cell[1]

    @property
    def center(self):
        """Its tile nearest to the middle of its tiles."""
        if self._center is None:
            mx = sum(x for x, _ in self.tiles) / len(self.tiles)
            my = sum(y for _, y in self.tiles) / len(self.tiles)
            self._center = min(self.tiles, key=lambda t: ((t[0] - mx) ** 2 + (t[1] - my) ** 2, t))
        return self._center

    def contains(self, map_id, x, y):
        return map_id == self.map_id and (x >> CELL_BITS, y >> CELL_BITS) == self.cell

    def __repr__(self):
        return '<Ground {} {},{}>'.format(self.map_id, *self.center)


def cell_of(x, y):
    return x >> CELL_BITS, y >> CELL_BITS


def load_grounds(game):
    """Map -> cell -> Ground for the cells with monsters, from the world's spawns."""
    per_spawn = defaultdict(int)
    for mob in game.monsters.values():
        if mob.attackable:
            per_spawn[mob.spawn] += 1
    grounds = defaultdict(dict)
    for spawn, n in sorted(per_spawn.items(), key=lambda s: (s[0].map_id, s[0].number, s[0].xs.start, s[0].ys.start)):
        terrain = game.maps[spawn.map_id].terrain
        tiles = [(x, y) for y in spawn.ys for x in spawn.xs if terrain.walkable(x, y) and not terrain.safe(x, y)]
        if not tiles:
            continue
        share = n / len(tiles)
        cells = grounds[spawn.map_id]
        for x, y in tiles:
            cell = cell_of(x, y)
            g = cells.get(cell)
            if g is None:
                g = cells[cell] = Ground(spawn.map_id, cell, [
                    (cx, cy) for cy in range(cell[1] * CELL, (cell[1] + 1) * CELL)
                    for cx in range(cell[0] * CELL, (cell[0] + 1) * CELL)
                    if terrain.walkable(cx, cy) and not terrain.safe(cx, cy)])
            g.counts[spawn.number] = g.counts.get(spawn.number, 0.0) + share
    return grounds


def around(ground, grounds):
    """Monster type -> monsters of ground and half of those of the cells around it, and its tiles counted the same
    way."""
    counts = defaultdict(float)
    tiles = 0.0
    cx, cy = ground.cell
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            g = grounds.get((cx + dx, cy + dy))
            if g is None:
                continue
            weight = 1.0 if g is ground else NEIGHBOURS
            tiles += len(g.tiles) * weight
            for t, n in g.counts.items():
                counts[t] += n * weight
    return counts, tiles


def deadly_cells(grounds, fights):
    """The cells of a map's grounds where monsters that would kill the bot are (fights: type -> Fight)."""
    return frozenset(cell for cell, g in grounds.items()
                     if any(n >= DEADLY and fights[t].deadly for t, n in around(g, grounds)[0].items()))


class _Mean:
    """An rng whose draw is the mean: monster_exp's random half on average."""

    @staticmethod
    def randrange(n):
        return (n - 1) / 2


def hit_chance(attack_rate, defense_rate):
    """Share of hits that land, combat.hit_check's rule."""
    if attack_rate < defense_rate:
        return combat.MIN_HIT_CHANCE / 100
    return 1.0 if attack_rate <= 0 else (attack_rate - defense_rate) / attack_rate


@dataclass
class Fight:
    """What fighting a monster type costs a bot and brings it, on average."""
    kill_time: float  # seconds of swings or casts
    dps: float  # life per second it takes while it fights back (monsters that look for players)
    exp: float
    ok: bool  # killed in time for no more life than the bot's risk allows
    deadly: bool  # it looks, and a fight with it would take about all the bot's life

    @property
    def damage(self):
        return self.dps * self.kill_time


def attack(p, skill=None):
    """(min, max, share %) ranges of a hit and the seconds between hits: the skill (a SkillInfo with damage) or the
    weapon, at the client's pace (mup.bot.motor)."""
    v = p.values
    if skill is not None:
        lo, hi = v.magic_min + skill.damage, v.magic_max + skill.damage + skill.damage // 2
        return [(lo, hi, 100 + v.staff_rise)], motor.CAST_TIME / (1 + v.magic_speed / 100)
    return combat.weapon_ranges(p), motor.SWING_TIME / (1 + v.attack_speed / 100)


def fight(p, info, exp_rate=1.0, skill=None, risk=0.5):
    """A fight of p's player against a monster of MonsterInfo info, with skill (SkillInfo) or the weapon."""
    v = p.values
    ranges, interval = attack(p, skill)
    rolled = sum((lo + hi) / 2 * share / 100 for lo, hi, share in ranges)
    per_hit = max(rolled - info.defense, combat.minimum_damage(p.level))
    kill_time = info.life / (per_hit * hit_chance(v.attack_rate, info.defense_rate)) * interval
    dps = 0.0
    if info.view_range > 0:
        taken = max((info.damage_min + info.damage_max) / 2 - v.defense, combat.minimum_damage(info.level))
        dps = hit_chance(info.attack_rate, v.defense_rate) * taken / max(info.attack_speed / 1000, 0.1)
    limit = p.max_life * (0.3 + 0.4 * risk)
    exp = experience.monster_exp(p.level, info.level, exp_rate, rng=_Mean)
    return Fight(kill_time, dps, exp, ok=kill_time <= MAX_KILL_TIME and dps * kill_time <= limit,
                 deadly=dps * min(kill_time, FIGHT_LIMIT) > p.max_life * DEADLY_LIFE)


def regen_rate(p):
    """Life per second the regeneration gives back (mup.server.combat.regen)."""
    return (max(1, int(p.max_life * combat.LIFE_REGEN)) + p.max_life * p.values.life_recovery // 100) \
        / combat.REGEN_INTERVAL


def best_skill(game, p):
    """The damaging skill p's player would hunt with: the most damage for its mana among those it knows and has the
    mana for at all, None for the weapon."""
    known = [game.skills[n] for n in p.skills if n is not None and n in game.skills]
    damaging = [s for s in known if s.damage > 0 and s.radius == 0 and s.mana <= p.max_mana]
    return max(damaging, key=lambda s: (s.damage, -s.mana, s.number), default=None)


def worth(game, p, ground, grounds, fights, others=0):
    """
    Exp per second p's player would make on ground (its map's grounds around it count half) and the monster types
    it would hunt for it, the band: of those it can kill, the most worth first while they add to it. fights: monster
    type -> Fight. others: players hunting there already. (0, ()) when it can't hunt there.
    """
    counts, tiles = around(ground, grounds)
    if any(n >= DEADLY and fights[t].deadly for t, n in counts.items()):
        return 0.0, ()
    regen = regen_rate(p)
    killable = {t: n for t, n in counts.items() if fights[t].ok}

    def per_kill(t, walk):
        """Seconds a kill of type t takes with the walk to it and the rest after it."""
        f = fights[t]
        fighting = f.kill_time + walk
        return fighting + max(0.0, f.damage - regen * fighting) / regen

    def value(band):
        total = sum(killable[t] for t in band)
        walk = math.sqrt(tiles / total) * motor.STEP_TIME
        demand = total / sum(killable[t] * per_kill(t, walk) for t in band)
        supply = sum(killable[t] / (game.monster_info[t].regen_time + fights[t].kill_time) for t in band)
        return min(demand, supply / (1 + others)) * sum(killable[t] * fights[t].exp for t in band) / total

    if sum(killable.values()) < MIN_MONSTERS:
        return 0.0, ()
    by_worth = sorted(killable, key=lambda t: (-fights[t].exp / per_kill(t, 0.0), t))
    best, band = 0.0, ()
    for i in range(1, len(by_worth) + 1):
        if sum(killable[t] for t in by_worth[:i]) < MIN_MONSTERS:
            continue
        v = value(by_worth[:i])
        if v > best:
            best, band = v, tuple(by_worth[:i])
    return best, band


def fights_for(game, p, types, risk=0.5):
    """Monster type -> Fight of p's player against types, with its best skill."""
    skill = best_skill(game, p)
    rate = game.config.exp_rate
    return {t: fight(p, game.monster_info[t], rate, skill, risk) for t in types}


def rank(game, p, grounds, travel=None, risk=0.5, rng=None, others=None, avoid=(), fights=None):
    """
    [(score, Ground, band)] of the grounds of a map (cell -> Ground) best first for p's player, band: the monster
    types it would hunt there (worth). travel(ground): steps to it, None when it can't be reached; others(ground):
    players there; avoid: ground keys left out; rng: the bot's own, for its liking; fights: fights_for the types of
    grounds when the caller has them.
    """
    if fights is None:
        fights = fights_for(game, p, {t for g in grounds.values() for t in g.counts}, risk)
    ranked = []
    for cell in sorted(grounds):
        g = grounds[cell]
        if g.key in avoid:
            continue
        value, band = worth(game, p, g, grounds, fights, others(g) if others else 0)
        if value <= 0:
            continue
        if travel is not None:
            steps = travel(g)
            if steps is None:
                continue
            value *= HORIZON / (HORIZON + steps * motor.STEP_TIME)
        if rng is not None:
            value *= 1 + rng.uniform(-VARIETY, VARIETY)
        ranked.append((value, g, band))
    ranked.sort(key=lambda r: (-r[0], r[1].key))
    return ranked


def next_point(p):
    """The stat (F3 06 number) the next level up point goes to: the one furthest below its share of the build."""
    shares = BUILDS[p.class_type.base]
    base = p.class_info
    spent = [p.strength - base.strength, p.agility - base.agility, p.vitality - base.vitality,
             p.energy - base.energy]
    total = sum(spent) + 1
    whole = sum(shares)
    return max(range(4), key=lambda i: (shares[i] * total / whole - spent[i], -i))


def built(class_type, level):
    """A player of class_type at level with its points spent by the build, its first skills and no items."""
    p = Player.new(class_type, level=level, skills=list(DEFAULT_SKILLS.get(class_type, [])))
    for _ in range((level - 1) * p.class_info.level_points):
        stat = stats.STATS[next_point(p)]
        setattr(p, stat, getattr(p, stat) + 1)
    p.values = stats.compute(p)
    p.life, p.mana = p.max_life, p.max_mana
    return p


def reachable_maps(gates, map_id, level, magic_gladiator=False):
    """The maps the gates lead to from map_id for a player of level, map_id with them."""
    seen = {map_id}
    todo = [map_id]
    while todo:
        m = todo.pop()
        for g in gates.values():
            if g.kind == gate.ENTRANCE and g.map_id == m and g.target in gates \
                    and level >= g.min_level(magic_gladiator):
                target = gates[g.target].map_id
                if target not in seen:
                    seen.add(target)
                    todo.append(target)
    return seen
