"""
Monster behaviour, run by the game tick for the monsters near players: wander around the spawn spot, chase a player
that comes within view range, attack it within attack range, return when it is lost or too far from home. NPCs
stand, traps hit who comes within their attack range, guards the murderers within theirs.
"""
import random
from mup.packet.server import SAction
from mup.server import combat, effect, monster, pk, summon, view
from mup.server.path import direction, find_path
from mup.server.world import VIEW_RANGE, distance

ACTIVE_RANGE = VIEW_RANGE + 4  # monsters this close to a player act, the others wait
ATTACK = 0x64  # 18 animation: the client picks the monster's attack animation
THINK = 0.5  # seconds between looks around while standing
WANDER_CHANCE = 0.15  # per look around
CHASE_STEPS = 2  # steps walked before looking at the target again
RETURN_STEPS = 8
LOST = 2  # times view range: a target this far is given up


def tick(game, m, now):
    active = set()
    for c in m.players:
        active.update(m.monsters.near(c.player.x, c.player.y, ACTIVE_RANGE))
    for mob in active:
        update(game, mob, now)


def update(game, mob, now):
    if mob.dead:
        return
    if mob.owner is not None:
        summon_update(game, mob, now)
        return
    if mob.npc:
        if mob.type_id in monster.TRAPS:
            trap_update(game, mob, now)
        elif mob.type_id in monster.GUARDS:
            guard_update(game, mob, now)
        return
    if mob.path and now >= mob.next_step_at:
        step(game, mob, now)
    if now < mob.next_think_at:
        return

    if mob.target is not None and not keeps_chasing(game, mob, mob.target):
        mob.target = None
        mob.returning = distance(mob.x, mob.y, *mob.home) > mob.info.move_range
    if mob.target is None and not mob.returning:
        mob.target = find_target(game, mob)
        if mob.target is not None:
            mob.path = mob.path[:1]  # finish the step it is on, then go for the target

    if mob.target is not None:
        chase(game, mob, now)
    elif mob.returning:
        go_home(game, mob, now)
    else:
        wander(game, mob, now)


def can_target(game, mob, c):
    p = c.player
    return (p is not None and c.playing and not p.dead and p.map_id == mob.map_id
            and not game.maps[p.map_id].terrain.safe(p.x, p.y))


def keeps_chasing(game, mob, c):
    if not can_target(game, mob, c):
        return False
    p = c.player
    return (distance(mob.x, mob.y, p.x, p.y) <= mob.info.view_range * LOST
            and distance(mob.x, mob.y, *mob.home) <= mob.spawn.leash)


def find_target(game, mob):
    """The nearest player in view range that can be attacked. View range 0: it doesn't look."""
    if mob.info.view_range <= 0:
        return None
    near = [c for c in game.maps[mob.map_id].players.near(mob.x, mob.y, mob.info.view_range)
            if can_target(game, mob, c)]
    if not near:
        return None
    return min(near, key=lambda c: (distance(mob.x, mob.y, c.player.x, c.player.y), random.random()))


def chase(game, mob, now):
    p = mob.target.player
    if mob.path:
        mob.next_think_at = mob.next_step_at
        return

    if distance(mob.x, mob.y, p.x, p.y) <= mob.info.attack_range:
        if now >= mob.next_attack_at:
            attack(game, mob, mob.target, now)
        mob.next_think_at = min(mob.next_attack_at, now + THINK)
        return

    m = game.maps[mob.map_id]
    path = find_path(m.monster_can_stand, (mob.x, mob.y), (p.x, p.y), reach=mob.info.attack_range,
                     max_steps=mob.info.view_range * LOST)
    if path:
        walk(game, mob, path[:CHASE_STEPS], now)
    else:
        mob.target = None
        mob.returning = True
        mob.next_think_at = now + THINK


def attack(game, mob, c, now):
    p = c.player
    facing = direction(p.x - mob.x, p.y - mob.y)
    if facing is not None:
        mob.direction = facing
    action = SAction(cid=mob.cid, direction=mob.direction, action=ATTACK, target=c.cid)
    for o in view.viewers(game, mob):
        o.write(action)
    mob.next_attack_at = now + mob.info.attack_speed / 1000
    combat.monster_attack(game, mob, c)


def trap_update(game, mob, now):
    """A trap hits the nearest player within its attack range, 0: standing on it (usual), at its attack speed."""
    if now < mob.next_attack_at:
        return
    near = [c for c in game.maps[mob.map_id].players.near(mob.x, mob.y, mob.info.attack_range)
            if can_target(game, mob, c)]
    if near:
        attack(game, mob, min(near, key=lambda c: distance(mob.x, mob.y, c.player.x, c.player.y)), now)


def guard_update(game, mob, now):
    """A guard hits the nearest murderer (mup.server.pk.PUNISHED) within its attack range, in a safe zone too, at
    its attack speed. It stays where it stands."""
    if now < mob.next_attack_at:
        return
    near = [c for c in game.maps[mob.map_id].players.near(mob.x, mob.y, mob.info.attack_range)
            if c.player is not None and c.playing and not c.player.dead and pk.refused(c)]
    if near:
        attack(game, mob, min(near, key=lambda c: distance(mob.x, mob.y, c.player.x, c.player.y)), now)


def go_home(game, mob, now):
    if mob.path:
        mob.next_think_at = mob.next_step_at
        return
    if distance(mob.x, mob.y, *mob.home) <= mob.info.move_range:
        mob.returning = False
        mob.next_think_at = now + THINK
        return

    m = game.maps[mob.map_id]
    path = find_path(m.monster_can_stand, (mob.x, mob.y), mob.home, reach=mob.info.move_range)
    if path:
        walk(game, mob, path[:RETURN_STEPS], now)
    else:
        # no way back from here, it lives here now
        mob.home = mob.x, mob.y
        mob.returning = False
        mob.next_think_at = now + THINK


def wander(game, mob, now):
    mob.next_think_at = now + THINK
    r = mob.info.move_range
    if mob.path or r <= 0 or random.random() >= WANDER_CHANCE:
        return
    m = game.maps[mob.map_id]
    hx, hy = mob.home
    goal = random.randint(hx - r, hx + r), random.randint(hy - r, hy + r)
    if goal == (mob.x, mob.y) or not m.monster_can_stand(*goal):
        return
    path = find_path(m.monster_can_stand, (mob.x, mob.y), goal, max_steps=r * 2, budget=200)
    if path:
        walk(game, mob, path, now)


def walk(game, mob, path, now):
    """Starts walking path, the players who see mob get one walk packet to its end."""
    mob.path = list(path)
    tx, ty = mob.path[-1]
    mob.direction = direction(tx - mob.x, ty - mob.y)
    mob.next_step_at = now + mob.info.move_speed / 1000
    mob.next_think_at = mob.next_step_at
    view.monster_walks(game, mob)


def step(game, mob, now):
    m = game.maps[mob.map_id]
    x, y = mob.path[0]
    if not m.monster_can_stand(x, y):
        # another monster got there first: stop, the walk to its own tile stops it in the clients
        mob.path = []
        view.monster_walks(game, mob)
        return
    mob.path.pop(0)
    m.move_monster(mob, x, y)
    view.monster_moved(game, mob)
    mob.next_step_at = now + mob.info.move_speed / 1000 * (2 if effect.ICE in mob.effects else 1)


FOLLOW = 2  # tiles a summon keeps from its owner
SUMMON_THINK = 0.3


def summon_update(game, mob, now):
    """A summon's turn: it goes for its target near its owner, otherwise follows the owner."""
    c = mob.owner
    p = c.player
    if p is None or p.dead or p.map_id != mob.map_id or c.summon is not mob:
        if c.summon is mob:
            summon.dismiss(game, c)
        else:
            summon.gone(game, mob)
        return
    if mob.path and now >= mob.next_step_at:
        step(game, mob, now)
    if now < mob.next_think_at or mob.path:
        return
    mob.next_think_at = now + SUMMON_THINK

    t = mob.target
    if t is not None and (t.dead or t.map_id != mob.map_id or distance(t.x, t.y, p.x, p.y) > summon.GUARD):
        mob.target = t = None
    if t is not None:
        if distance(mob.x, mob.y, t.x, t.y) <= mob.info.attack_range:
            if now >= mob.next_attack_at:
                summon_attack(game, mob, t, now)
            return
        summon_walk(game, mob, (t.x, t.y), mob.info.attack_range, now)
    elif distance(mob.x, mob.y, p.x, p.y) > FOLLOW:
        summon_walk(game, mob, (p.x, p.y), FOLLOW, now)


def summon_walk(game, mob, goal, reach, now):
    m = game.maps[mob.map_id]
    path = find_path(m.monster_can_stand, (mob.x, mob.y), goal, reach=reach, max_steps=summon.GUARD * 2)
    if path:
        walk(game, mob, path[:CHASE_STEPS * 2], now)


def summon_attack(game, mob, target, now):
    """A summon hits a monster like a monster hits a player: miss check, its damage less the defense. The damage
    counts as its owner's."""
    facing = direction(target.x - mob.x, target.y - mob.y)
    if facing is not None:
        mob.direction = facing
    action = SAction(cid=mob.cid, direction=mob.direction, action=ATTACK, target=target.cid)
    for o in view.viewers(game, mob):
        o.write(action)
    mob.next_attack_at = now + mob.info.attack_speed / 1000
    i = mob.info
    dmg = 0
    if combat.hit_check(i.attack_rate, target.info.defense_rate):
        dmg = max(random.randint(i.damage_min, i.damage_max) - target.info.defense, combat.minimum_damage(i.level))
    combat.hit_monster(mob.owner, target, dmg, magic=True)
    if target.dead:
        mob.target = None
