"""
A bot's brain: it perceives what a client is shown and knows (its own character, the objects in its view, the packets
it gets, the game's data files), never a monster's life, target or path or anything out of view. Every 0.5..1 s it
picks the activity by priority (survive > spend points > items > level, mup.bot.activity) and steps it, with reflexes
on top: a potion or a heal in a fight, the elf's buffs and summon. The career (mup.bot.career) picks the hunting
ground, on its map or one the gates lead to; the gear (mup.bot.gear) what its items are worth; the town
(mup.bot.town) when a trip to the NPCs is due and what it does there. Everything it decides goes to the trace
(BotManager.trace).
"""
import logging
from collections import Counter
from mup.bot import career, gear, town
from mup.bot.activity import (Activity, Dead, Escape, Rest, SpendPoints, Equip, Loot, Trip, Spot, Travel, Hunt,
                              Idle, FAILED, LEVEL)
from mup.bot.motor import AREA_REACH, AREA_TARGETS, TALK_REACH
from mup.model.item import GRID, GroundItem
from mup.model.monster import Monster
from mup.model.player import CharacterClass
from mup.packet.server import (SAction, SChaosClosed, SDurability, SInventory, SItemDeleted, SItemList, SKill,
                               SLevelUp, SMapMove, SMoveItemResult, SPickUpResult, SPointResult, SRepairResult,
                               SRespawn, SSellResult, SSkillChange, STalk, SWarehouseClosed)
from mup.server import casting, combat, effect, ground as grounds, inventory, summon
from mup.server.world import distance

logger = logging.getLogger(__name__)

THINK = (0.5, 1.0)  # seconds between thinks, drawn each time
ATTACKED = 3.0  # seconds a monster that swung next to it counts as attacking it
LEAVE_ALONE = 120.0  # seconds a monster it couldn't reach or kill is left alone
TRIES = 3  # failed paths to a monster before it is left alone
STUCK = 300.0  # seconds without exp and without moving: the watchdog's flag
STAY = 0.9  # the ground it hunted on before it logged in is kept while it is worth this share of the best
AVOID = 600.0  # seconds a ground it gave up on is left out
DEATHS = 2  # deaths on a ground before it is given up
ESCAPES = 5  # escapes on a ground before it is given up
MAP_DEATHS = 3  # deaths on a map it came to through a gate before it goes back where it came from
AVOID_MAP = 1800.0  # seconds a map it gave up on is left out, and until it gained MAP_LEVELS
MAP_LEVELS = 2
MAP_STAY = 1200.0  # seconds it hunts on a map it came to before it looks at the others again
MAP_MARGIN = 1.1  # a ground of another map is worth this much more than the best of its own map before it goes
POTION_REST = 0.5  # with a full stock of healing potions it rests below this share of its rest threshold
LOOT_RANGE = 12  # tiles from it an item on the ground may lie that it goes for
LOOT_TRIES = 2  # pick ups of an item before it is left there: refused in its owner time, once more after it
ZEN = 0.05  # worth of zen on the ground, it takes no room
TRIP_LOOK = 5.0  # seconds its errands (mup.bot.town.errands) are kept before it looks again
OFFER_TIME = 60.0  # seconds the best upgrade of the shops is kept, unless its items, values or zen change
TRIP_ESCAPES = 2  # escapes on the way to town before the trip waits like a failed one
DRAINED = 600.0  # seconds its kills on a ground count against it: the monsters respawn anywhere in their spawn area,
# most of them away from the ground


class Brain:
    def __init__(self, c):
        self.c = c
        self.rng = c.rng
        self.personality = c.bot.personality
        self.activity: Activity = None
        self.next_think_at = 0.0
        self.last_tick = None
        self.ground = None  # mup.bot.career.Ground it hunts on, of its map or another
        self.band = ()  # monster types it hunts there
        self.deadly = frozenset()  # cells of its map where monsters would kill it
        self.deadly_map = None  # the map they are of
        self.blocked = frozenset()  # of them the cells it keeps out of: all but those around it
        self.repick = True  # the ground is picked again at the next level activity
        self.stored = tuple(c.bot.career['ground']) if c.bot.career.get('ground') else None  # from its last login
        self.avoid = {}  # ground key -> until when it is left out
        self.deaths_on = Counter()  # ground key -> deaths there
        self.escapes_on = Counter()  # ground key -> escapes there
        self.left_alone = {}  # monster cid -> until when
        self.tries = Counter()  # monster cid -> failed paths
        self.attacked_by = {}  # monster cid -> when it last swung next to it
        self.kills = 0
        self.hunted = 0.0  # seconds it hunted since its last kill or since it picked its ground
        self.killed_on = {}  # ground key -> times of its kills there, the last DRAINED seconds
        self.fights = {}  # monster type -> mup.bot.career.Fight at its level, values and items (fight)
        self.progress = None  # (exp, map, x, y) and when it changed, for the watchdog
        self.progress_at = 0.0
        self.map_id = None  # the map it knows it is on
        self.came_from = None  # the map it came from through a gate
        self.came_at = None  # when
        self.visited = {}  # map -> game time it first was there, for the report
        self.deaths_in = Counter()  # map -> deaths since it came there
        self.avoid_maps = {}  # map -> (until when, until which level) it is left out
        self.worth = {}  # item serial -> mup.bot.gear.value, until its values or items change
        self.looted = {}  # GroundItem -> (pick ups refused, not again before)
        self._change = self._goal = None  # mup.bot.gear.best_change and goal, made when first asked for
        self.dirty = True  # its items or values changed: _change and _goal are made again
        self.resume = False  # it looted or put on an item while hunting: it hunts on where it stands
        self.interrupted = None  # the activity the last switch dropped
        self.window = None  # the NPC window it was shown (30), STalk's kinds, until it closes
        self.talking = None  # the NPC it talked to last, whose window that is
        self.goods = {}  # shop slot -> Item, the goods of the shop it talks to (31)
        self.vault = {}  # vault slot -> Item, its vault's window (31)
        self.trip_after = 0.0  # the next town trip not before
        self.trip_escapes = 0  # escapes from the trips since the last one ended
        self.refused_at = -1.0  # when the server last refused it a buy or a sale
        self._errands = None  # (when, (due, along)) of mup.bot.town.errands
        self._offer = None  # (when, budget, mup.bot.town.Offer) of the best upgrade in the shops

    @property
    def player(self):
        return self.c.player

    def start(self, now):
        self.next_think_at = now + self.rng.uniform(0.0, THINK[1])  # staggered
        self.progress_at = now
        self.map_id = self.player.map_id
        self.visited.setdefault(self.map_id, now)

    def event(self, kind, **values):
        self.c.event(kind, **values)

    def career_state(self):
        return {'ground': list(self.ground.key) if self.ground is not None else None}

    # perception

    def perceive(self, packets, now):
        c = self.c
        p = c.player
        for packet in packets:
            if isinstance(packet, SKill):
                if packet.cid == c.cid:
                    c.counts['deaths'] += 1
                    self.event('died', by=packet.killer)
                    if self.ground is not None:
                        self.deaths_on[self.ground.key] += 1
                    self.died_on_map(now)
                elif packet.killer == c.cid:
                    c.counts['kills'] += 1  # for the report: the client doesn't read the killer
                if isinstance(self.activity, Hunt) and self.activity.target is not None \
                        and packet.cid == self.activity.target.cid:
                    self.kills += 1
                    self.hunted = 0.0
                    if self.ground is not None:
                        self.killed_on.setdefault(self.ground.key, []).append(now)
                    self.event('kill', target=packet.cid)
            elif isinstance(packet, SAction):
                mob = c.server.monsters.get(packet.cid)
                if mob is not None and mob in c.view and p is not None \
                        and distance(mob.x, mob.y, p.x, p.y) <= mob.info.attack_range + 1:
                    self.attacked_by[packet.cid] = now
            elif isinstance(packet, (SPointResult, SSkillChange, SInventory)):
                self.changed()  # its values, its skills, its items
            elif isinstance(packet, SLevelUp):
                self.changed()
                c.counts['levels'] += 1
                self.event('level', level=packet.level)
                self.repick = True
            elif isinstance(packet, SPickUpResult):
                self.dirty = True  # into the grid
            elif isinstance(packet, SMoveItemResult):
                self.changed()  # what it wears
            elif isinstance(packet, (SItemDeleted, SDurability)):
                if packet.slot < GRID and (isinstance(packet, SItemDeleted) or packet.durability == 0):
                    self.changed()
                elif isinstance(packet, SItemDeleted):
                    self.dirty = True
            elif isinstance(packet, (SSellResult, SRepairResult)):
                self.changed()  # its items, their durability
            elif isinstance(packet, STalk):
                self.window, self.goods = packet.window, {}
            elif isinstance(packet, SItemList):
                if packet.kind == SItemList.SHOP and self.window in (STalk.SHOP, STalk.WAREHOUSE):
                    found = {e['slot']: gear.decoded(c.server, e['item']) for e in packet.entries}
                    found = {slot: i for slot, i in found.items() if i is not None}
                    if self.window == STalk.SHOP:
                        self.goods = found
                    else:
                        self.vault = found
            elif isinstance(packet, (SWarehouseClosed, SChaosClosed)):
                self.window, self.goods = None, {}
            elif isinstance(packet, SRespawn):
                self.window, self.goods = None, {}
                c.motor.stop()
                c.motor.walk_ends_at = now
                self.entered(packet.map)
                self.event('respawn', map=packet.map, x=packet.x, y=packet.y)
            elif isinstance(packet, SMapMove) and packet.map_change:
                self.window, self.goods = None, {}
                self.repick = True
                if packet.map != self.map_id:
                    self.came_from, self.came_at = self.map_id, now
                    self.deaths_in[packet.map] = 0
                    self.visited.setdefault(packet.map, now)
                self.entered(packet.map)
                self.event('map', map=packet.map, x=packet.x, y=packet.y)
        picked = c.motor.picked
        if picked is not None:
            c.motor.picked = None
            self.picked(*picked, now)
        motor = c.motor
        if motor.bought is not None:
            if motor.bought is False:
                self.refused_at = now
                self.event('not bought')
            else:
                c.counts['bought'] += 1
                c.counts['spent'] += motor.bought
            motor.bought = None
            self._errands = self._offer = None
        if motor.sold is not None:
            if motor.sold is False:
                self.refused_at = now
                self.event('not sold')
            else:
                c.counts['sold'] += 1
                c.counts['sold zen'] += motor.sold
            motor.sold = None
        if motor.repaired is not None:
            c.counts['repairs'] += 1
            c.counts['repair zen'] += motor.repaired
            motor.repaired = None

    def changed(self):
        """Its values, skills or items changed: the fights and the worth of items are weighed again."""
        self.fights = {}
        self.worth = {}
        self.dirty = True
        self._errands = self._offer = None

    def entered(self, map_id):
        """It is on map_id (a gate, a respawn): the cells that would kill it there."""
        self.map_id = map_id
        self.deadly, self.deadly_map = self.deadly_of(map_id), map_id
        self.keep_out()

    def fights_with(self, types):
        """self.fights with those of types it has none for yet."""
        missing = set(types) - set(self.fights)
        if missing:
            self.fights.update(career.fights_for(self.c.server, self.player, missing, self.personality.risk))
        return self.fights

    def deadly_of(self, map_id):
        """The cells of map_id where monsters would kill it (mup.bot.career.deadly_cells)."""
        grounds_there = self.c.manager.grounds.get(map_id, {})
        fights = self.fights_with({t for g in grounds_there.values() for t in g.counts})
        return career.deadly_cells(grounds_there, fights)

    def died_on_map(self, now):
        """A death on a map it came to: after MAP_DEATHS there it goes back, the map is left out for a while."""
        m = self.player.map_id
        self.deaths_in[m] += 1
        if self.came_from is not None and m != self.came_from and self.deaths_in[m] >= MAP_DEATHS:
            self.deaths_in[m] = 0
            self.avoid_maps[m] = now + AVOID_MAP, self.player.level + MAP_LEVELS
            self.event('give up map', map=m, back_to=self.came_from)
            self.ground = None
            self.repick = True

    def threats(self, now):
        """Living monsters in view that look for players and are near enough to come, or attack it."""
        p = self.player
        found = []
        for o in self.c.view:
            if isinstance(o, Monster) and o.attackable and not o.dead:
                if self.attacked_by.get(o.cid, -ATTACKED) > now - ATTACKED or (
                        o.info.view_range > 0 and distance(o.x, o.y, p.x, p.y) <= o.info.view_range + 2):
                    found.append(o)
        return found

    def dangers(self, now):
        """Monsters in view it runs from: one hitting it whose fight takes more life than its risk allows or that it
        can't get at (a ranged one on a gate), one that would kill it about to notice it. None in the safe zone,
        monsters don't go for players there."""
        p = self.player
        found = []
        if self.c.server.maps[p.map_id].terrain.safe(p.x, p.y):
            return found
        for o in self.c.view:
            if isinstance(o, Monster) and o.attackable and not o.dead:
                f = self.fight(o.type_id)
                if self.attacked_by.get(o.cid, -ATTACKED) > now - ATTACKED and (
                        not f.ok or self.left_alone.get(o.cid, 0.0) > now or not self.reachable(o)) or (
                        f.deadly and distance(o.x, o.y, p.x, p.y) <= o.info.view_range + 1):
                    found.append(o)
        return found

    def reachable(self, o):
        """A tile it walks on is within its weapon's reach of monster o, it can get at it."""
        walkable = self.c.walkable
        r = self.c.motor.walk_reach()
        return any(walkable(o.x + dx, o.y + dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1))

    def unsafe(self, x, y):
        """A monster in view that would kill it is about to notice who stands at x, y."""
        for o in self.c.view:
            if isinstance(o, Monster) and o.attackable and not o.dead and self.fight(o.type_id).deadly \
                    and distance(o.x, o.y, x, y) <= o.info.view_range + 2:
                return True
        return False

    def attacker(self, now):
        """The nearest monster in view that swung next to it lately, None."""
        p = self.player
        found = [o for o in self.c.view if isinstance(o, Monster) and not o.dead and o.attackable
                 and self.attacked_by.get(o.cid, -ATTACKED) > now - ATTACKED]
        return min(found, key=lambda o: (distance(o.x, o.y, p.x, p.y), o.cid), default=None)

    def choose_target(self, now, band, attacker=None, fit=True):
        """An attacker it can fight and get at first, then the nearest monster in view of the band; neither left
        alone, nor where it can't get at them. Of the band those whose fight leaves it above its rest threshold (fit:
        False, whatever its life) and that don't stand where a monster would kill it."""
        if attacker is not None and self.fight(attacker.type_id).ok and self.left_alone.get(attacker.cid, 0.0) <= now \
                and self.reachable(attacker):
            return attacker
        p = self.player
        found = [o for o in self.c.view if isinstance(o, Monster) and not o.dead and o.attackable
                 and o.type_id in band and self.left_alone.get(o.cid, 0.0) <= now and self.reachable(o)
                 and (not fit or self.fit_for(o.type_id)) and not self.unsafe(o.x, o.y)]
        return min(found, key=lambda o: (distance(o.x, o.y, p.x, p.y), o.cid), default=None)

    def fight(self, type_id):
        """mup.bot.career.Fight against a monster of type_id at its level and values, kept until they change."""
        f = self.fights.get(type_id)
        if f is None:
            c = self.c
            f = self.fights[type_id] = career.fights_for(c.server, self.player, [type_id],
                                                         self.personality.risk)[type_id]
        return f

    def rest_below(self):
        """Share of its life it rests below: its personality's, less with healing potions to drink in a fight."""
        have = sum(i.durability for _, i in gear.potions(self.player, gear.HEALING))
        return self.personality.rest_below * (1 - POTION_REST * min(have, gear.KEEP) / gear.KEEP)

    def fit_for(self, type_id):
        """It has the life for a fight with a monster of type_id: what the fight takes on average leaves it above
        its rest threshold."""
        p = self.player
        return p.life - self.fight(type_id).taken >= p.max_life * self.rest_below()

    def skill(self, mob):
        """The skill number it attacks mob with now, None for the weapon: of the skills that hit one target, and the
        area ones counting the monsters around mob, the most damage per second it has the mana for now."""
        c, p = self.c, self.player
        game = c.server
        info = mob.info
        best, most = None, career.landed(p, *career.attack(p), info.defense, info.defense_rate, p.level)
        skills = career.attack_skills(game, p) + self.area_skills()
        around = None
        for s in sorted(skills, key=lambda s: s.number):
            if p.mana < s.mana:
                continue
            rate = career.landed(p, *career.attack(p, s), info.defense, info.defense_rate, p.level)
            if s.radius:
                if around is None:
                    around = sum(1 for o in c.view if isinstance(o, Monster) and o.attackable and not o.dead
                                 and distance(o.x, o.y, mob.x, mob.y) <= AREA_REACH)
                rate *= min(around, casting.SHOTS.get(s.number, AREA_TARGETS))
            if rate > most:
                best, most = s.number, rate
        return best

    def area_skills(self):
        """The damaging area skills it knows (1E)."""
        game, p = self.c.server, self.player
        return [game.skills[n] for n in p.skills if n is not None and n in game.skills and game.skills[n].radius
                and n not in casting.NO_DAMAGE and game.skills[n].mana <= p.max_mana]

    def unreachable(self, cid, now):
        self.tries[cid] += 1
        self.event('unreachable', target=cid, tries=self.tries[cid])
        if self.tries[cid] >= TRIES:
            self.leave_alone(cid, now)

    def leave_alone(self, cid, now):
        self.tries.pop(cid, None)
        self.left_alone[cid] = now + LEAVE_ALONE
        self.event('left alone', target=cid)

    def nearby_cells(self, ground):
        """The cells of ground and of the grounds around it that it doesn't keep out of."""
        grounds_here = self.c.manager.grounds.get(ground.map_id, {})
        cx, cy = ground.cell
        return {(cx + dx, cy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                if (cx + dx, cy + dy) in grounds_here and (cx + dx, cy + dy) not in self.blocked} | {ground.cell}

    # items

    def types(self):
        """The monster types its items are weighed against: its band, else those it can fight."""
        if self.band:
            return tuple(self.band)
        return tuple(sorted(t for t, f in self.fights.items() if f.ok))

    def value(self, item, source=None):
        """mup.bot.gear.value of item (in grid slot source, None: on the ground), kept until its values or items
        change; potions are weighed by how many it has."""
        if gear.potion_kind(item) is not None:
            return gear.value(self.c.server, self.player, item, (), self.personality.risk, source)
        v = self.worth.get(item.serial)
        if v is None:
            v = self.worth[item.serial] = gear.value(self.c.server, self.player, item, self.types(),
                                                     self.personality.risk, source)
        return v

    def worth_of(self, item, source=None):
        """What item is worth to it, to use or to sell (mup.bot.gear.sale)."""
        return max(self.value(item, source), gear.sale(item))

    def best_change(self):
        """mup.bot.gear.best_change of its grid, made again when its items or values changed."""
        self._update()
        return self._change

    def goal(self):
        """mup.bot.gear.goal: the stats a piece it will soon wear asks for."""
        self._update()
        return self._goal

    def _update(self):
        if self.dirty:
            self.dirty = False
            game, p, types, risk = self.c.server, self.player, self.types(), self.personality.risk
            self._change = gear.best_change(game, p, types, risk)
            self._goal = gear.goal(game, p, types, risk)

    def scroll(self):
        """The grid slot of a scroll or orb it can learn now, None."""
        game, p = self.c.server, self.player
        return next((slot for slot, item in sorted(p.inventory.items())
                     if slot >= GRID and gear.learnable(game, p, item)), None)

    def loot_value(self, g):
        """What ground item g is worth to it: zen a little, an item by the gear, to use or to sell."""
        return ZEN if g.item is None else self.worth_of(g.item)

    def junk(self, than):
        """The grid slot of its item worth least, if less than than: what it drops to make room. None."""
        p = self.player
        found = [(self.worth_of(i, slot), -i.info.width * i.info.height, slot)
                 for slot, i in p.inventory.items() if slot >= GRID]
        least = min(found, default=None)
        return least[2] if least is not None and least[0] < than else None

    def loot(self, now):
        """The nearest item on the ground in view worth picking up with room for it (or junk to drop for it), not
        given up and not where a monster would kill it. None."""
        p = self.player
        found = []
        for g in self.c.view:
            if not isinstance(g, GroundItem) or distance(g.x, g.y, p.x, p.y) > LOOT_RANGE:
                continue
            tries, until = self.looted.get(g, (0, 0.0))
            if tries >= LOOT_TRIES or until > now or self.unsafe(g.x, g.y):
                continue
            worth = self.loot_value(g)
            if worth <= 0:
                continue
            if g.item is not None and inventory.free_slot(p.inventory, g.item.info) is None \
                    and self.junk(worth) is None:
                continue
            found.append((distance(g.x, g.y, p.x, p.y), g.id, g))
        return min(found)[2] if found else None

    def picked(self, g, ok, now):
        """The answer to its pick up of g."""
        c = self.c
        if ok:
            self.looted.pop(g, None)
            if g.item is None:
                c.counts['zen'] += g.zen
            else:
                c.counts['items'] += 1
            self.event('picked', item=g.item.info.name if g.item is not None else 'zen')
            return
        tries, _ = self.looted.get(g, (0, 0.0))
        self.looted[g] = tries + 1, now + grounds.OWNER_TIME  # another's for a while, the server's rule
        self.event('not picked', ground_item=g.id, tries=tries + 1)

    # town

    def errands(self, now, again=False):
        """mup.bot.town.errands, kept for TRIP_LOOK seconds or until its items, values or level change; again: looked
        at anew."""
        if again or self._errands is None or now - self._errands[0] > TRIP_LOOK:
            self._errands = now, town.errands(self, now)
        return self._errands[1]

    def trip_due(self, now):
        """A town trip is due: an errand is, a trip isn't waiting."""
        return now >= self.trip_after and bool(self.errands(now)[0])

    def upgrade(self, now, budget):
        """mup.bot.town.offer for budget, kept for OFFER_TIME seconds while the budget pays for it and didn't grow by
        a tenth, or until its items, values or level change."""
        kept = self._offer
        if kept is None or now - kept[0] > OFFER_TIME or budget > kept[1] * 1.1 or \
                kept[2] is not None and kept[2].price > budget:
            self._offer = kept = now, budget, town.offer(self, budget)
        return kept[2]

    def map_steps(self):
        """Map -> steps along the best route there, for the maps the gates lead to from where it stands."""
        c, p = self.c, self.player
        routes = c.manager.flows.routes(p.map_id, p.x, p.y, p.level,
                                        p.class_type.base == CharacterClass.MAGIC_GLADIATOR, self.blocked)
        steps = {}
        for r in routes.values():
            m = c.server.gates[r.arrival].map_id
            steps[m] = min(steps.get(m, r.steps), r.steps)
        return steps

    def spot(self, n):
        """The Spot next to mup.bot.town.Npc n it walks to before it talks: the tiles within TALK_REACH it walks on."""
        walkable = self.c.manager.flows.walkable(n.map_id)
        tiles = [(n.x + dx, n.y + dy) for dy in range(-TALK_REACH, TALK_REACH + 1)
                 for dx in range(-TALK_REACH, TALK_REACH + 1) if (dx, dy) != (0, 0) and walkable(n.x + dx, n.y + dy)]
        return Spot(n.map_id, ('npc', n.type_id, n.x, n.y), tiles)

    def npc_near(self, n):
        """The NPC in its view that mup.bot.town.Npc n is, None."""
        return next((o for o in self.c.view if isinstance(o, Monster) and o.npc and o.type_id == n.type_id
                     and o.map_id == n.map_id and (o.spawn.xs.start, o.spawn.ys.start) == (n.x, n.y)), None)

    def talk(self, npc):
        """30 to npc next to it: the window it opens comes as the answer."""
        self.talking, self.window, self.goods = npc, None, {}
        self.c.motor.talk(npc)

    # reflexes

    def reflexes(self, now):
        """In a fight: a heal or a potion below its threshold, mana for its skill; the elf's summon and buffs while
        she hunts."""
        c, p, motor = self.c, self.player, self.c.motor
        attacked = self.attacker(now) is not None or isinstance(self.activity, Escape)
        if attacked and p.life < p.max_life * self.personality.potion_below:
            if motor.cast(casting.HEAL, c.cid, now):
                self.event('cast', skill=casting.HEAL)
                return
            slot = gear.potion_for(p, gear.HEALING)
            if slot is not None:
                name, life = p.inventory[slot].info.name, p.life
                if motor.use(slot, now):
                    c.counts['potions'] += 1
                    self.event('drink', potion=name, life=life)
                    return
        if motor.target is not None and (attacked or isinstance(self.activity, Hunt)):
            best = career.best_skill(c.server, p)
            if best is not None and p.mana < best.mana:
                slot = gear.potion_for(p, gear.MANA)
                if slot is not None:
                    name, mana = p.inventory[slot].info.name, p.mana
                    if motor.use(slot, now):
                        c.counts['potions'] += 1
                        self.event('drink', potion=name, mana=mana)
                        return
        if isinstance(self.activity, Hunt) and motor.target is not None:
            self.buff(now)

    def buff(self, now):
        """The elf's summon when she has none, her greater defense and damage when they ran out (19 on herself)."""
        c, p, motor = self.c, self.player, self.c.motor
        if c.summon is None or c.summon.dead:
            calls = [n for n in p.skills if n in casting.SUMMONS and c.server.skills[n].mana <= p.mana
                     and p.map_id not in summon.NOT_ON]
            if calls and motor.cast(max(calls), c.cid, now):
                self.event('cast', skill=max(calls))
                return
        for number in (effect.GREATER_DEFENSE, effect.GREATER_DAMAGE):
            if number in p.skills and number not in p.effects and motor.cast(number, c.cid, now):
                self.event('cast', skill=number)
                return

    # thinking

    def tick(self, now):
        if self.last_tick is not None and self.activity is not None:
            self.c.counts['time ' + self.activity.name] += now - self.last_tick
            if isinstance(self.activity, Hunt):
                self.hunted += now - self.last_tick
        self.last_tick = now
        if now >= self.next_think_at:
            self.next_think_at = now + self.rng.uniform(*THINK)
            if self.player is not None:
                self.think(now)

    def think(self, now):
        self.watchdog(now)
        if not self.player.dead:
            self.reflexes(now)
        want = self.wanted(now)
        a = self.activity
        if want is not None:
            if a is None or a.priority > want.priority:
                self.switch(want(self, now), now)
        elif a is None:
            self.switch(self.level_activity(now), now)
        elif isinstance(a, (Travel, Loot, Equip, Trip)) and self.ground is not None \
                and self.attacker(now) is not None:
            self.switch(Hunt(self, now, self.ground, self.band), now)
        a = self.activity
        if a.timeout is not None and now - a.started > a.timeout:
            self.finish(FAILED, now, 'timeout')
            return
        status = a.step(now)
        if status is not None:
            self.finish(status, now)

    def wanted(self, now):
        """The class of the most urgent activity it wants, None when it may level. It runs from what it can't fight,
        rests below its threshold and when a hunt found nothing it has the life for; with no monster at it, it picks
        up what it wants, wears its upgrades and goes to town when a trip is due."""
        p = self.player
        if p.dead:
            return Dead
        if self.dangers(now):
            return Escape
        if p.life < p.max_life * self.rest_below() or (isinstance(self.activity, Hunt) and self.activity.unfit):
            return Rest
        if p.free_points > 0:
            return SpendPoints
        if combat.ammunition(p) is False and self.best_change() is not None:
            return Equip  # a bow without arrows can't fight back: off with it, or a stack in the hand, at once
        if self.attacker(now) is None:
            if self.loot(now) is not None:
                return Loot
            if self.scroll() is not None or self.best_change() is not None:
                return Equip
            if self.trip_due(now):
                return Trip
        return None

    def level_activity(self, now):
        p = self.player
        if self.repick or self.ground is None:
            self.pick_ground(now)
        resume, self.resume = self.resume, False
        if self.ground is None:
            return Idle(self, now)
        self.keep_out()
        g = self.ground
        if g.contains(p.map_id, p.x, p.y) or self.attacker(now) is not None or resume and g.map_id == p.map_id \
                and distance(p.x, p.y, *g.center) <= Hunt.AWAY:
            return Hunt(self, now, g, self.band)
        return Travel(self, now, g)

    def switch(self, activity, now):
        if self.activity is not None:
            self.event('dropped', activity=self.activity.name)
        self.interrupted = self.activity
        self.activity = activity
        self.event('pick', **activity.details())
        if isinstance(activity, Escape) and isinstance(self.interrupted, Trip):
            self.trip_escapes += 1  # something in the way to town: not the ground's
            if self.trip_escapes >= TRIP_ESCAPES:
                self.trip_escapes = 0
                self.trip_after = now + Trip.PAUSE
                self.event('give up trip', why='escapes')
        elif isinstance(activity, Escape) and self.ground is not None:
            self.escapes_on[self.ground.key] += 1
            if self.escapes_on[self.ground.key] >= ESCAPES:
                self.escapes_on.pop(self.ground.key)
                self.give_up_ground(now, 'escapes')

    def finish(self, status, now, why=None):
        a = self.activity
        why = why or a.why
        self.event(status, activity=a.name, **({'why': why} if why else {}))
        self.activity = None
        self.resume = isinstance(a, (Loot, Equip)) and isinstance(self.interrupted, Hunt)
        self.c.motor.stop()
        if isinstance(a, Trip):
            self.trip_escapes = 0
        if a.priority == LEVEL and status == FAILED and self.ground is not None:
            self.give_up_ground(now, why)
        if isinstance(a, Dead) and self.ground is not None and self.deaths_on[self.ground.key] >= DEATHS:
            self.deaths_on.pop(self.ground.key)
            self.give_up_ground(now, 'deaths')

    def give_up_ground(self, now, why):
        self.avoid[self.ground.key] = now + AVOID
        self.event('give up', ground=list(self.ground.key), why=why)
        self.ground = None
        self.repick = True

    def pick_ground(self, now):
        """The best ground by the career of its map and the maps the gates lead to at its level (but those it gave up
        on), from where it stands. On another map the walk counts the way through the gates and around the cells it
        would keep out of there, it is weighed against a longer stay and the ground has to be worth MAP_MARGIN more
        than those of its map; on a map it came to it stays MAP_STAY first, while it finds a ground there."""
        c, p = self.c, self.player
        self.repick = False
        game, manager = c.server, c.manager
        flows = manager.flows
        self.fights = {}
        self.entered(p.map_id)
        routes = flows.routes(p.map_id, p.x, p.y, p.level, p.class_type.base == CharacterClass.MAGIC_GLADIATOR,
                              self.blocked)
        maps = {p.map_id} | {game.gates[r.arrival].map_id for r in routes.values()}
        avoided = {m for m, (until, level) in self.avoid_maps.items() if until > now or p.level < level}
        maps = (maps - avoided) or maps
        fights = self.fights_with({t for m in maps for g in manager.grounds.get(m, {}).values() for t in g.counts})
        self.worth = {}
        self.dirty = True  # the band its items are weighed against may change
        self._errands = self._offer = None
        here = flows.from_tile(p.map_id, p.x, p.y, self.blocked)
        avoid = {k for k, until in self.avoid.items() if until > now}
        players = [o.player for o in c.view if not isinstance(o, (Monster, GroundItem)) and o.player is not None]
        staying = self.came_at is not None and now - self.came_at < MAP_STAY
        for k in list(self.killed_on):
            self.killed_on[k] = [t for t in self.killed_on[k] if t > now - DRAINED]
            if not self.killed_on[k]:
                del self.killed_on[k]

        def others(g):
            """Players hunting ground g, and its own kills there lately as hunters that share the respawns."""
            drained = len(self.killed_on.get(g.key, ())) / max(1.0, sum(g.counts.values()))
            return sum(g.contains(o.map_id, o.x, o.y) for o in players) + drained

        def ranked_on(m):
            if m == p.map_id:
                travel, horizon = (lambda g: here.distance(*g.center)), career.HORIZON
            else:
                arrivals = [r for r in routes.values() if game.gates[r.arrival].map_id == m]
                deadly = self.deadly_of(m)
                travel, horizon = (lambda g: self.way_steps(arrivals, deadly, g)), career.MAP_HORIZON
            return [(value if m == p.map_id else value / MAP_MARGIN, g, band) for value, g, band in career.rank(
                game, p, manager.grounds.get(m, {}), travel=travel, risk=self.personality.risk, rng=self.rng,
                others=others, avoid=avoid, fights=fights, horizon=horizon)]

        ranked = ranked_on(p.map_id) if p.map_id in maps else []
        if not (staying and ranked):
            ranked += [r for m in sorted(maps - {p.map_id}) for r in ranked_on(m)]
        ranked.sort(key=lambda r: (-r[0], r[1].key))
        if not ranked:
            self.ground, self.band = None, ()
            self.event('no ground')
            return
        value, ground, self.band = ranked[0]
        stored = next((r for r in ranked if r[1].key == self.stored), None)
        self.stored = None
        if stored is not None and stored[0] >= value * STAY:
            value, ground, self.band = stored
        if self.ground is None or ground.key != self.ground.key:
            self.hunted = 0.0
        self.ground = ground
        self.event('ground', ground=list(self.ground.key), center=list(self.ground.center),
                   worth=round(value, 3), band=list(self.band))

    def way_steps(self, arrivals, deadly, g):
        """Steps to ground g of another map along the best of the routes to its arrival areas, around the deadly
        cells of that map but those of the arrival area. None when there is no way."""
        flows = self.c.manager.flows
        gates = self.c.server.gates
        best = None
        for r in arrivals:
            exit_gate = gates[r.arrival]
            at = {career.cell_of(x, y) for x in exit_gate.xs for y in exit_gate.ys}
            d = flows.arrival(r.arrival, deadly - at).distance(*g.center)
            if d is not None and (best is None or r.steps + d < best):
                best = r.steps + d
        return best

    def way(self, ground):
        """The flow field it walks down towards ground from where it stands around the cells it keeps out of (but
        those around an NPC it goes to): the ground's on its map, else the one to the first gate of the best route
        there. None when there is no way."""
        c, p = self.c, self.player
        flows = c.manager.flows
        self.keep_out()  # from where it stands now
        if ground.map_id == p.map_id:
            blocked = self.blocked
            if isinstance(ground, Spot):  # an NPC: players walk there, it runs from what shows up on the way
                cx, cy = career.cell_of(*ground.center)
                blocked = blocked - {(cx + dx, cy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
            return flows.field(p.map_id, ('ground',) + ground.key, lambda: ground.tiles, blocked)
        routes = flows.routes(p.map_id, p.x, p.y, p.level, p.class_type.base == CharacterClass.MAGIC_GLADIATOR,
                              self.blocked)
        deadly = self.deadly_of(ground.map_id)
        best = None
        for r in routes.values():
            if c.server.gates[r.arrival].map_id == ground.map_id:
                d = self.way_steps([r], deadly, ground)
                if d is not None and (best is None or d < best[0]):
                    best = d, r
        if best is None:
            return None
        return flows.gate(best[1].gates[0], self.blocked)

    def keep_out(self):
        """The deadly cells it keeps out of from where it stands: all of them, but those around it when it stands
        next to one (it has to get out)."""
        p = self.player
        if self.deadly_map != p.map_id:
            self.deadly = frozenset()  # of another map, until it knows this one's
        cx, cy = career.cell_of(p.x, p.y)
        around = {(cx + dx, cy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        self.blocked = self.deadly - around if around & self.deadly else self.deadly

    def watchdog(self, now):
        """No exp and no step for STUCK seconds while it should be levelling: flagged, the activity and the ground
        dropped."""
        p = self.player
        state = p.exp, p.map_id, p.x, p.y
        if state != self.progress or not isinstance(self.activity, (Hunt, Travel)):
            self.progress, self.progress_at = state, now
            return
        if now - self.progress_at > STUCK:
            self.c.counts['stuck'] += 1
            self.event('stuck', seconds=round(now - self.progress_at))
            self.progress_at = now
            self.finish(FAILED, now, 'stuck')
