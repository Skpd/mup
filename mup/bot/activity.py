"""
What a bot is doing: small state machines the brain picks by priority (mup.bot.brain). step(now) runs at every
think and returns None while it goes on, DONE or FAILED when it ended; past its timeout (if it has one) it failed.
"""
from dataclasses import dataclass
from typing import List, Tuple
from mup.bot import career, gear
from mup.bot.motor import TALK_REACH
from mup.model.monster import Monster
from mup.packet.client import CAddPoint
from mup.packet.server import STalk
from mup.server import ai, inventory
from mup.server.path import find_path
from mup.server.world import VIEW_RANGE, distance

DONE, FAILED = 'done', 'failed'
# priorities, lower first: survive > spend points > items > level
DEAD, ESCAPE, REST, POINTS, ITEMS, LEVEL = 0, 1, 2, 3, 4, 5
TOWN = 40  # steps to the safe zone a bot runs for when it flees
FLEE_BUDGET = 600  # tiles looked at for a way out


class Activity:
    name = None
    priority = LEVEL
    timeout = None  # game seconds

    def __init__(self, brain, now):
        self.brain = brain
        self.c = brain.c
        self.started = now
        self.why = None  # of a failure, for the trace

    def fail(self, why):
        self.why = why
        return FAILED

    @property
    def player(self):
        return self.c.player

    @property
    def motor(self):
        return self.c.motor

    def step(self, now):
        raise NotImplementedError

    def details(self):
        """What the trace tells about it when it is picked."""
        return {}


class Dead(Activity):
    """Lies dead until the respawn (F3 04)."""
    name = 'dead'
    priority = DEAD
    timeout = 30.0

    def step(self, now):
        self.motor.stop()
        return DONE if not self.player.dead else None


def flee(activity, threats, now):
    """Away from threats: to the safe zone when it is near (around the cells the bot keeps out of), else out of their
    chase (twice their view range, ai.LOST) to the tile furthest from them."""
    c, motor, brain = activity.c, activity.motor, activity.brain
    p = c.player
    safe = c.manager.flows.safe(p.map_id, brain.blocked)
    d = safe.distance(p.x, p.y)
    if d is not None and d <= TOWN:
        if motor.flow is not safe:
            motor.follow(safe)
        return
    if motor.busy(now):
        return
    walkable = c.walkable
    r = min(VIEW_RANGE, max(o.info.view_range * ai.LOST + 1 for o in threats))
    ring = [(p.x + dx, p.y + dy) for dx in range(-r, r + 1) for dy in ((-r, r) if abs(dx) < r else range(-r, r + 1))
            if walkable(p.x + dx, p.y + dy)]
    for goal in sorted(ring, key=lambda t: (-min(distance(t[0], t[1], o.x, o.y) for o in threats), t))[:3]:
        path = find_path(walkable, (p.x, p.y), goal, max_steps=r * 2, budget=FLEE_BUDGET)
        if path:
            motor.go(path)
            return


class Escape(Activity):
    """A monster it can't afford to fight is after it: it runs (flee) until none has been near for a while."""
    name = 'escape'
    priority = ESCAPE
    timeout = 120.0
    CLEAR = 5.0  # seconds without danger before it stops

    def __init__(self, brain, now):
        super().__init__(brain, now)
        self.clear_at = None

    def step(self, now):
        dangers = self.brain.dangers(now)
        p = self.player
        if self.c.server.maps[p.map_id].terrain.safe(p.x, p.y):
            return DONE
        if dangers:
            self.clear_at = None
            flee(self, dangers, now)
            return None
        if self.clear_at is None:
            self.clear_at = now + self.CLEAR
        return DONE if now >= self.clear_at else None


class Rest(Activity):
    """Low on life: away from the monsters that look (flee), then it stands until the regeneration gave its life
    back."""
    name = 'rest'
    priority = REST
    timeout = 900.0

    def step(self, now):
        p, motor, brain = self.player, self.motor, self.brain
        if p.life >= p.max_life * max(brain.personality.rest_until, brain.rest_below()):
            return DONE
        threats = brain.threats(now)
        if self.c.server.maps[p.map_id].terrain.safe(p.x, p.y) or not threats:
            motor.stop()
            return None
        flee(self, threats, now)
        return None


class SpendPoints(Activity):
    """Level up points into the stats, F3 06 one at a time (the answer comes at once): first what a piece it will
    soon wear asks for (mup.bot.gear.goal), then by the class build."""
    name = 'points'
    priority = POINTS
    timeout = 30.0
    PER_THINK = 5

    def step(self, now):
        p = self.player
        goal = self.brain.goal()
        for _ in range(self.PER_THINK):
            if p.free_points <= 0:
                return DONE
            self.c.send(CAddPoint(stat=career.next_point(p, goal)))
        return DONE if p.free_points <= 0 else None


class Loot(Activity):
    """
    Picks up what it wants of the items on the ground in its view (mup.bot.brain.loot), nearest first: walks next to
    it and sends 22, one at a time. With its grid full it drops what is worth least to it first, when that is worth
    less. An item refused (another's for a while) is tried once more after the owner time, then left.
    """
    name = 'loot'
    priority = ITEMS
    timeout = 60.0

    def step(self, now):
        brain, motor, p = self.brain, self.motor, self.player
        if motor.item is not None or motor.handling():
            return None
        g = brain.loot(now)
        if g is None:
            return DONE
        if g.item is not None and inventory.free_slot(p.inventory, g.item.info) is None:
            slot = brain.junk(brain.loot_value(g))
            if slot is not None:
                name = p.inventory[slot].info.name  # the answer comes at once
                if motor.drop(slot):
                    brain.event('drop', item=name, room_for=g.item.info.name)
            return None
        motor.pick_up(g)
        brain.event('loot', item=g.item.info.name if g.item is not None else 'zen', x=g.x, y=g.y)
        return None


class Equip(Activity):
    """
    Learns the scrolls and orbs it can (26), wears the upgrades of its grid (mup.bot.gear.best_change) one 24 at a
    time: what has to leave the slot and the hands goes to the grid first, or on the ground when it is worth nothing
    more or there is no room, then the piece goes on.
    """
    name = 'equip'
    priority = ITEMS
    timeout = 30.0

    def step(self, now):
        brain, motor, p = self.brain, self.motor, self.player
        if motor.handling():
            return None
        slot = brain.scroll()
        if slot is not None:
            item = p.inventory[slot]
            if motor.use(slot, now):
                self.c.counts['learned'] += 1
                brain.event('learn', item=item.info.name)
            return None
        change = brain.best_change()
        if change is None:
            return DONE
        game = self.c.server
        for s in change.out:
            piece = p.inventory.get(s)
            if piece is None:
                continue
            after = gear.trial(game, p, change.after)
            free = inventory.free_slot(p.inventory, piece.info)
            if free is not None and gear.value(game, after, piece, brain.types(), brain.personality.risk) > 0:
                motor.move_item(s, free)
                brain.event('take off', item=piece.info.name, slot=s)
            else:
                motor.drop(s)
                brain.event('drop', item=piece.info.name, slot=s)
            return None
        for source, s, item in change.wear:
            if p.inventory.get(s) is item:
                continue
            if source is None or p.inventory.get(source) is not item:
                return self.fail('the item moved')
            motor.move_item(source, s)
            self.c.counts['worn'] += 1
            brain.event('wear', item=item.info.name, slot=s, gain=round(change.gain, 3))
            return None
        return None


@dataclass
class Spot:
    """A place to walk to that isn't a hunting ground, the tiles next to an NPC: Travel goes there like to a
    ground (mup.bot.career.Ground's map_id, key, tiles, center, contains)."""
    map_id: int
    key: Tuple
    tiles: List[Tuple[int, int]]

    @property
    def center(self):
        return self.tiles[0]

    def contains(self, map_id, x, y):
        return map_id == self.map_id and (x, y) in self.tiles


class Restock(Activity):
    """
    Buys arrows or bolts for its bow or crossbow (mup.bot.brain.Brain.ammunition_needed) from the nearest shop that
    sells them, on its map or through the gates: walks next to the NPC, talks to it (30), buys stacks (32) one at a
    time, the best level it can afford (Brain.offer), until it has STACKS more or the zen runs out, then goes. The
    client sends nothing when a shop window closes, the server closes it when the player walks off. Equip wears
    them with the bow. A trip that failed isn't tried again for a while.
    """
    name = 'restock'
    priority = ITEMS
    timeout = 900.0
    TALK_WAIT = 3.0  # seconds for the shop window after 30
    STACKS = 4  # stacks it buys on a trip, of the best level STACKS of which cost at most half its zen
    PAUSE = 300.0  # seconds after a trip that failed before the next

    def __init__(self, brain, now):
        super().__init__(brain, now)
        self.ammo = brain.ammunition_needed(now)
        found = brain.seller(self.ammo) if self.ammo is not None else None
        self.npc_type, self.spot = found if found is not None else (None, None)
        self.walk = Travel(brain, now, self.spot) if self.spot is not None else None
        self.talked_at = None
        self.bought = 0

    def details(self):
        if self.spot is None:
            return {}
        return {'ammo': self.c.server.item_info[self.ammo].name, 'npc': self.npc_type, 'map': self.spot.map_id,
                'to': list(self.spot.center)}

    def fail(self, why):
        self.brain.restock_after = self.c.server.now + self.PAUSE
        return super().fail(why)

    def step(self, now):
        brain, motor, p = self.brain, self.motor, self.player
        if self.walk is None:
            return self.fail('no shop')
        if motor.handling():
            return None
        if brain.window == STalk.SHOP and brain.goods:
            if self.bought >= self.STACKS or gear.shots(p, self.ammo) >= self.STACKS * self.stack():
                return DONE
            offer = brain.offer(self.ammo)
            if offer is None:
                return DONE if self.bought else self.fail('no zen')
            slot, price, item = offer
            if inventory.free_slot(p.inventory, item.info) is None:
                junk = brain.junk(gear.POTION)
                if junk is None:
                    return DONE if self.bought else self.fail('no room')
                name = p.inventory[junk].info.name
                if motor.drop(junk):
                    brain.event('drop', item=name, room_for=item.info.name)
                return None
            if motor.buy(slot):
                self.bought += 1
                brain.event('buy', item=item.info.name, level=item.level, price=price)
            return None
        if self.talked_at is not None:
            if now - self.talked_at < self.TALK_WAIT:
                return None
            return self.fail('no shop window')
        npc = next((o for o in self.c.view if isinstance(o, Monster) and o.npc and o.type_id == self.npc_type), None)
        if npc is not None and p.map_id == npc.map_id and distance(p.x, p.y, npc.x, npc.y) <= TALK_REACH \
                and not motor.walking(now):
            motor.stop()
            motor.talk(npc)
            self.talked_at = now
            return None
        status = self.walk.step(now)
        if status == FAILED:
            return self.fail(self.walk.why)
        if status == DONE and npc is None:
            return self.fail('nobody there')
        return None

    def stack(self):
        return self.c.server.item_info[self.ammo].durability


class Travel(Activity):
    """Walks to a hunting ground down a flow field around the cells it keeps out of: the ground's on its map, else
    the way to the first gate of the route there (mup.bot.brain.way), the motor goes through it. Fails when it can't
    get there or stops getting closer."""
    name = 'travel'
    timeout = 1800.0
    NO_PROGRESS = 30.0  # seconds without getting closer

    def __init__(self, brain, now, ground):
        super().__init__(brain, now)
        self.ground = ground
        self.field = None
        self.map_id = None  # the map the field is of
        self.best = None
        self.progress_at = now

    def details(self):
        return {'to': list(self.ground.center), 'map': self.ground.map_id}

    def step(self, now):
        p, motor = self.player, self.motor
        if self.ground.contains(p.map_id, p.x, p.y):
            motor.stop()
            return DONE
        if motor.loading_until is not None:
            return None
        if self.map_id != p.map_id:  # it came here: the way on from here
            self.map_id, self.best, self.progress_at = p.map_id, None, now
            self.field = self.brain.way(self.ground)
            if self.field is None:
                return self.fail('no way there')
            if self.ground.map_id != p.map_id:
                self.brain.event('route', map=p.map_id, to_map=self.ground.map_id)
        d = self.field.distance(p.x, p.y)
        if d is None:
            return self.fail('no way there')
        if self.best is None or d < self.best:
            self.best, self.progress_at = d, now
        elif now - self.progress_at > self.NO_PROGRESS:
            return self.fail('no progress')
        if motor.flow is not self.field:
            motor.follow(self.field)
        return None


class Hunt(Activity):
    """
    Hunts on its ground: the monsters that attack it first, then those of its band nearest first, each until its 17
    or until it takes too long; a monster it can't reach is left alone after a few tries. With none in view it walks
    about the ground. Done when it wandered off the ground with nothing to fight or the brain wants another ground,
    failed when it killed nothing for a long time since it picked the ground (mup.bot.brain.Brain.kill_at), hunts
    of it before counting.
    """
    name = 'hunt'
    timeout = None
    TARGET_TIME = 90.0  # seconds a target may take before it is left alone
    IDLE = 90.0  # seconds without a kill before the ground is given up
    AWAY = 24  # tiles from the ground's center it may chase to
    ROAM = 12  # tiles to the spots it walks to
    ROAM_DRAWS = 8
    ROAM_BUDGET = 600

    def __init__(self, brain, now, ground, band):
        super().__init__(brain, now)
        self.ground = ground
        self.band = set(band)
        self.target = None
        self.target_since = now
        self.unfit = False  # monsters of its band are in view but it hasn't the life to fight them

    def details(self):
        return {'ground': list(self.ground.center)}

    def step(self, now):
        brain, motor, p = self.brain, self.motor, self.player
        if motor.unreachable is not None:
            brain.unreachable(motor.unreachable, now)
            motor.unreachable = None
            self.target = None
        mob = self.target
        if mob is not None and (mob.dead or mob not in self.c.view):
            mob = self.target = None
        if mob is not None and now - self.target_since > self.TARGET_TIME:
            brain.leave_alone(mob.cid, now)
            motor.stop()
            mob = self.target = None
        attacker = brain.attacker(now)
        if attacker is not None and attacker is not mob:
            mob = None  # one hitting it goes first
        if mob is None:
            mob = brain.choose_target(now, self.band, attacker)
            if mob is not None:
                self.target, self.target_since = mob, now
                brain.event('target', target=mob.cid, type=mob.type_id)
        self.unfit = mob is None and brain.choose_target(now, self.band, fit=False) is not None
        if mob is not None:
            motor.attack(mob, brain.skill(mob))
            return None
        if brain.repick:
            return DONE
        if now - brain.kill_at > self.IDLE:
            return self.fail('nothing killed')
        if distance(p.x, p.y, *self.ground.center) > self.AWAY:
            return DONE
        if not motor.busy(now):
            self.roam()
        return None

    def roam(self):
        """A walk to a random tile not too far of its ground or the grounds around, its center when none was
        drawn."""
        p, brain = self.player, self.brain
        cells = brain.nearby_cells(self.ground)
        walkable = self.c.walkable
        goal = self.ground.center
        for _ in range(self.ROAM_DRAWS):
            x, y = p.x + brain.rng.randint(-self.ROAM, self.ROAM), p.y + brain.rng.randint(-self.ROAM, self.ROAM)
            if career.cell_of(x, y) in cells and walkable(x, y) and not brain.unsafe(x, y):
                goal = x, y
                break
        path = find_path(walkable, (p.x, p.y), goal, max_steps=self.ROAM * 2, budget=self.ROAM_BUDGET)
        if path:
            self.motor.go(path)


class Idle(Activity):
    """Nowhere worth hunting: it stands, then looks again."""
    name = 'idle'
    timeout = 60.0

    def step(self, now):
        self.motor.stop()
        return None
