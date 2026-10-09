"""
What a bot is doing: small state machines the brain picks by priority (mup.bot.brain). step(now) runs at every
think and returns None while it goes on, DONE or FAILED when it ended; past its timeout (if it has one) it failed.
"""
from dataclasses import dataclass
from typing import List, Tuple
from mup.bot import career, gear, town
from mup.bot.motor import TALK_REACH
from mup.bot.town import AMMO, MANA, POTIONS, REPAIR, SELL, UPGRADE, VAULT
from mup.packet.client import CAddPoint
from mup.packet.server import STalk
from mup.server import ai, inventory, item as items, shop
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
    if motor.target is not None or motor.item is not None and motor.waiting is None:
        motor.stop()  # the attack or pick up it was on
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
    time: what has to leave the slot and the hands goes to the grid first (to keep or to sell), or on the ground when
    it is worth nothing more or there is no room, then the piece goes on.
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
            if free is not None and (gear.value(game, after, piece, brain.types(), brain.personality.risk) > 0
                                     or gear.sale(piece) > 0):
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


class Trip(Activity):
    """
    A town trip (mup.bot.town): the errands due and those it does along with them, at the stops of the plan in
    order. At each it walks next to the NPC and talks to it (30). At a shop it sells what it doesn't use (33, one at a
    time), repairs at a smith's (34: all, else the most worn pieces it can pay), buys (32, one at a time) potions,
    arrows or bolts and an upgrade, each within what the errands before it leave (town.reserve). At the vault it
    stores its jewels (24) and closes it (82). The client sends nothing when a shop window closes, the server closes
    it when the player walks off. Equip wears what it bought afterwards. A trip that failed or left an errand that
    was due undone isn't made again for a while.
    """
    name = 'trip'
    priority = ITEMS
    timeout = 900.0
    TALK_WAIT = 3.0  # seconds for the window after 30
    PAUSE = 300.0  # seconds after a trip that failed before the next

    def __init__(self, brain, now):
        super().__init__(brain, now)
        self.due, self.errands = brain.errands(now)
        self.stops = town.plan(brain, self.due, self.errands)
        self.index = -1
        self.walk = None
        self.talked_at = None
        self.asked = set()  # slots it asked the smith to repair at this stop
        self.upgraded = False
        self.c.counts['trips'] += 1
        self.next_stop(now)

    def details(self):
        return {'due': sorted(self.due), 'stops': [[s.npc.type_id, s.npc.map_id, *sorted(s.errands)]
                                                   for s in self.stops]}

    def fail(self, why):
        self.brain.trip_after = self.c.server.now + self.PAUSE
        return super().fail(why)

    @property
    def stop(self):
        return self.stops[self.index] if self.index < len(self.stops) else None

    def next_stop(self, now):
        self.index += 1
        self.talked_at = None
        self.asked = set()
        self.walk = None
        while self.stop is not None and not self.needed(self.stop):
            self.index += 1
        if self.stop is not None:
            self.walk = Travel(self.brain, now, self.brain.spot(self.stop.npc))

    def step(self, now):
        brain, motor, p = self.brain, self.motor, self.player
        if not self.stops:
            return self.fail('nowhere')
        if brain.refused_at >= self.started:
            return self.fail('refused')
        stop = self.stop
        if stop is None:
            return self.done(now)
        if motor.handling():
            return None
        npc = brain.npc_near(stop.npc)
        if brain.window is not None and npc is not None and brain.talking is npc:
            if not self.act(stop):
                self.next_stop(now)
            return None
        if self.talked_at is not None:
            if now - self.talked_at < self.TALK_WAIT:
                return None
            return self.fail('no window')
        if npc is not None and p.map_id == npc.map_id and distance(p.x, p.y, npc.x, npc.y) <= TALK_REACH \
                and not motor.walking(now):
            motor.stop()
            brain.talk(npc)
            self.talked_at = now
            return None
        status = self.walk.step(now)
        if status == FAILED:
            return self.fail(self.walk.why)
        if status == DONE and npc is None:
            return self.fail('nobody there')
        return None

    def done(self, now):
        """The last stop: done, but a due errand it couldn't do waits like a failed trip."""
        p = self.player
        undone = {SELL: lambda: town.free_tiles(p) < town.FULL and town.junk(self.brain),
                  REPAIR: lambda: town.worn(p, town.REPAIR_DUE, equipment=True),
                  POTIONS: lambda: town.have(p, gear.HEALING) < town.LOW,
                  AMMO: self.short_of_ammo,
                  UPGRADE: lambda: not self.upgraded,
                  VAULT: lambda: town.free_tiles(p) < town.FULL and town.jewels(p)}
        left = [k for k in self.due if undone[k]()]
        if left:
            self.brain.trip_after = now + self.PAUSE
            self.brain.event('undone', errands=sorted(left))
        return DONE

    def needed(self, stop):
        """Something is left to do at stop."""
        p, kinds = self.player, stop.errands
        if stop.npc.shop is None:
            return VAULT in kinds and bool(town.jewels(p))
        return any((SELL in self.errands and town.junk(self.brain, self.keep()),
                    REPAIR in kinds and town.worn(p),
                    POTIONS in kinds and town.have(p, gear.HEALING) < gear.STOCK,
                    MANA in kinds and town.have(p, gear.MANA) < gear.STOCK,
                    AMMO in kinds and self.short_of_ammo(),
                    UPGRADE in kinds and not self.upgraded))

    def keep(self):
        """Types it doesn't sell on this trip: the arrows or bolts it buys."""
        return (self.errands[AMMO],) if AMMO in self.errands else ()

    def short_of_ammo(self):
        ammo = self.errands[AMMO]
        return gear.shots(self.player, ammo) < town.STACKS * (self.c.server.item_info[ammo].durability or 1)

    def act(self, stop):
        """One request at stop's open window: True when it sent one, False when nothing is left there."""
        brain, motor, p = self.brain, self.motor, self.player
        if brain.window == STalk.WAREHOUSE:
            return self.store()
        if brain.window != STalk.SHOP or not brain.goods:
            return False
        if SELL in self.errands:
            for slot, item, gold in town.junk(brain, self.keep()):
                if motor.sell(slot):
                    brain.event('sell', item=item.info.name, price=gold)
                return True
        if REPAIR in stop.errands and stop.npc.type_id in shop.REPAIRERS and self.repair():
            return True
        for kind in (POTIONS, AMMO, UPGRADE, MANA):
            if kind in stop.errands and self.buy(kind):
                return True
        return False

    def repair(self):
        """34 for all when it can pay for all, else for the most worn piece it can pay. True when it asked."""
        brain, motor, p = self.brain, self.motor, self.player
        pieces = [w for w in town.worn(p) if w[0] not in self.asked]
        if not pieces:
            return False
        total = town.repair_cost(p)
        if total <= p.zen:
            self.asked |= {slot for slot, _ in town.worn(p, 1.0)}
            motor.repair()
            brain.event('repair', items=len(pieces), cost=total)
            return True
        for slot, item in sorted(pieces, key=lambda w: (w[1].durability / items.max_durability(w[1]), w[0])):
            self.asked.add(slot)
            gold = shop.repair_cost(item, 0)
            if gold <= p.zen:
                motor.repair(slot)
                brain.event('repair', item=item.info.name, cost=gold)
                return True
        return False

    def buy(self, kind):
        """32 for what errand kind buys at this shop within its budget: a stack of potions, of arrows or bolts, the
        upgrade. With no room for it, the item worth least to it (it sold its junk) goes on the ground first. True
        when it sent one of them."""
        brain, motor, p = self.brain, self.motor, self.player
        goods = brain.goods
        budget = p.zen - town.reserve(brain, self.errands, kind)
        if kind in (POTIONS, MANA):
            potion = gear.HEALING if kind == POTIONS else gear.MANA
            if town.have(p, potion) >= gear.STOCK:
                return False
            choice = town.potion_choice(p, goods, potion, brain.personality.potion_below, budget)
        elif kind == AMMO:
            if not self.short_of_ammo():
                return False
            choice = town.ammo_choice(p, goods, self.errands[AMMO])
            if choice is not None and choice[1] > budget:
                choice = None
        else:
            o = self.errands[UPGRADE]
            item = goods.get(o.slot)
            if self.upgraded or item is None or (item.type, item.level) != (o.item.type, o.item.level) \
                    or o.price > budget:
                return False
            choice = o.slot, o.price, item
        if choice is None:
            return False
        slot, gold, item = choice
        if inventory.free_slot(p.inventory, item.info) is None:
            junk = brain.junk(gear.POTION if kind != UPGRADE else brain.worth_of(item))
            if junk is None:
                return False
            name = p.inventory[junk].info.name
            if motor.drop(junk):
                brain.event('drop', item=name, room_for=item.info.name)
            return True
        if motor.buy(slot):
            if kind == UPGRADE:
                self.upgraded = True
            brain.event('buy', item=item.info.name, level=item.level, price=gold)
        return True

    def store(self):
        """24 for a jewel of its grid into the vault's first free slot, 82 when none is left. True when it moved
        one."""
        brain, motor, p = self.brain, self.motor, self.player
        if VAULT in self.stop.errands:
            for slot, item in town.jewels(p):
                target = inventory.free_slot(brain.vault, item.info, inventory.WAREHOUSE)
                if target is None:
                    break
                if motor.store(slot, target):
                    brain.vault[target] = item
                    self.c.counts['stored'] += 1
                    brain.event('store', item=item.info.name, slot=target)
                return True
        motor.close_vault()
        brain.window = None
        return False


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
    failed when it hunted a long time since it picked the ground without a kill (mup.bot.brain.Brain.hunted: the
    hunts of it before count, the walks there, rests and town trips not).
    """
    name = 'hunt'
    timeout = None
    TARGET_TIME = 90.0  # seconds a target may take before it is left alone
    IDLE = 90.0  # seconds of hunting without a kill before the ground is given up
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
        if brain.hunted > self.IDLE:
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
    """Nowhere worth hunting from where it stands: it walks to the safe zone, through the cells it keeps out of (they
    may close it in where it fled to), stands, then looks again."""
    name = 'idle'
    timeout = 60.0

    def step(self, now):
        p, motor = self.player, self.motor
        field = self.c.manager.flows.safe(p.map_id)
        if self.c.server.maps[p.map_id].terrain.safe(p.x, p.y) or field.distance(p.x, p.y) is None:
            motor.stop()
        elif motor.flow is not field:
            motor.follow(field)
        return None
