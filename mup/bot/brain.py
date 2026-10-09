"""
A bot's brain: it perceives what a client is shown and knows (its own character, the objects in its view, the packets
it gets, the game's data files), never a monster's life, target or path or anything out of view. Every 0.5..1 s it
picks the activity by priority (survive > spend points > level, mup.bot.activity) and steps it; the career
(mup.bot.career) picks the hunting ground. Everything it decides goes to the trace (BotManager.trace).
"""
import logging
from collections import Counter
from mup.bot import career
from mup.bot.activity import (Activity, Dead, Escape, Rest, SpendPoints, Travel, Hunt, Idle, FAILED, LEVEL)
from mup.model.item import GroundItem
from mup.model.monster import Monster
from mup.packet.server import SAction, SKill, SLevelUp, SMapMove, SPointResult, SRespawn
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


class Brain:
    def __init__(self, c):
        self.c = c
        self.rng = c.rng
        self.personality = c.bot.personality
        self.activity: Activity = None
        self.next_think_at = 0.0
        self.last_tick = None
        self.ground = None  # mup.bot.career.Ground it hunts on
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
        self.fights = {}  # monster type -> mup.bot.career.Fight at its level and values (fight)
        self.progress = None  # (exp, map, x, y) and when it changed, for the watchdog
        self.progress_at = 0.0

    @property
    def player(self):
        return self.c.player

    def start(self, now):
        self.next_think_at = now + self.rng.uniform(0.0, THINK[1])  # staggered
        self.progress_at = now

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
                elif packet.killer == c.cid:
                    c.counts['kills'] += 1  # for the report: the client doesn't read the killer
                if isinstance(self.activity, Hunt) and self.activity.target is not None \
                        and packet.cid == self.activity.target.cid:
                    self.kills += 1
                    self.event('kill', target=packet.cid)
            elif isinstance(packet, SAction):
                mob = c.server.monsters.get(packet.cid)
                if mob is not None and mob in c.view and p is not None \
                        and distance(mob.x, mob.y, p.x, p.y) <= mob.info.attack_range + 1:
                    self.attacked_by[packet.cid] = now
            elif isinstance(packet, SPointResult):
                self.fights = {}  # its values changed
            elif isinstance(packet, SLevelUp):
                self.fights = {}
                c.counts['levels'] += 1
                self.event('level', level=packet.level)
                self.repick = True
            elif isinstance(packet, SRespawn):
                c.motor.stop()
                c.motor.walk_ends_at = now
                self.keep_out()
                self.event('respawn', map=packet.map, x=packet.x, y=packet.y)
            elif isinstance(packet, SMapMove):
                c.motor.map_changed(now)
                self.repick = True
                self.keep_out()
                self.event('map', map=packet.map, x=packet.x, y=packet.y)

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
        """Monsters in view it runs from: one hitting it whose fight takes more life than its risk allows, one that
        would kill it about to notice it. None in the safe zone, monsters don't go for players there."""
        p = self.player
        found = []
        if self.c.server.maps[p.map_id].terrain.safe(p.x, p.y):
            return found
        for o in self.c.view:
            if isinstance(o, Monster) and o.attackable and not o.dead:
                f = self.fight(o.type_id)
                if self.attacked_by.get(o.cid, -ATTACKED) > now - ATTACKED and not f.ok or (
                        f.deadly and distance(o.x, o.y, p.x, p.y) <= o.info.view_range + 1):
                    found.append(o)
        return found

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
        """An attacker it can fight first, then the nearest monster in view of the band that isn't left alone and
        whose fight leaves it above its rest threshold (fit: False, whatever its life) and that doesn't stand where a
        monster would kill it."""
        if attacker is not None and self.fight(attacker.type_id).ok:
            return attacker
        p = self.player
        found = [o for o in self.c.view if isinstance(o, Monster) and not o.dead and o.attackable
                 and o.type_id in band and self.left_alone.get(o.cid, 0.0) <= now
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

    def fit_for(self, type_id):
        """It has the life for a fight with a monster of type_id: what the fight takes on average leaves it above
        its rest threshold."""
        p = self.player
        return p.life - self.fight(type_id).damage >= p.max_life * self.personality.rest_below

    def skill(self):
        """The skill number it fights with now, None for the weapon: its best damaging one while the mana lasts."""
        p = self.player
        best = career.best_skill(self.c.server, p)
        return best.number if best is not None and p.mana >= best.mana else None

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
        grounds = self.c.manager.grounds.get(ground.map_id, {})
        cx, cy = ground.cell
        return {(cx + dx, cy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                if (cx + dx, cy + dy) in grounds and (cx + dx, cy + dy) not in self.blocked} | {ground.cell}

    # thinking

    def tick(self, now):
        if self.last_tick is not None and self.activity is not None:
            self.c.counts['time ' + self.activity.name] += now - self.last_tick
        self.last_tick = now
        if now >= self.next_think_at:
            self.next_think_at = now + self.rng.uniform(*THINK)
            if self.player is not None:
                self.think(now)

    def think(self, now):
        self.watchdog(now)
        want = self.wanted()
        a = self.activity
        if want is not None:
            if a is None or a.priority > want.priority:
                self.switch(want(self, now), now)
        elif a is None:
            self.switch(self.level_activity(now), now)
        elif isinstance(a, Travel) and self.attacker(now) is not None:
            self.switch(Hunt(self, now, self.ground, self.band), now)
        a = self.activity
        if a.timeout is not None and now - a.started > a.timeout:
            self.finish(FAILED, now, 'timeout')
            return
        status = a.step(now)
        if status is not None:
            self.finish(status, now)

    def wanted(self):
        """The class of the most urgent activity it wants, None when it may level. It runs from what it can't fight,
        rests below its threshold and when a hunt found nothing it has the life for."""
        p = self.player
        if p.dead:
            return Dead
        if self.dangers(self.c.server.now):
            return Escape
        if p.life < p.max_life * self.personality.rest_below or (
                isinstance(self.activity, Hunt) and self.activity.unfit):
            return Rest
        if p.free_points > 0:
            return SpendPoints
        return None

    def level_activity(self, now):
        p = self.player
        if self.repick or self.ground is None or self.ground.map_id != p.map_id:
            self.pick_ground(now)
        if self.ground is None:
            return Idle(self, now)
        self.keep_out()
        if self.ground.contains(p.map_id, p.x, p.y) or self.attacker(now) is not None:
            return Hunt(self, now, self.ground, self.band)
        return Travel(self, now, self.ground, self.blocked)

    def switch(self, activity, now):
        if self.activity is not None:
            self.event('dropped', activity=self.activity.name)
        self.activity = activity
        self.event('pick', **activity.details())
        if isinstance(activity, Escape) and self.ground is not None:
            self.escapes_on[self.ground.key] += 1
            if self.escapes_on[self.ground.key] >= ESCAPES:
                self.escapes_on.pop(self.ground.key)
                self.give_up_ground(now, 'escapes')

    def finish(self, status, now, why=None):
        a = self.activity
        why = why or a.why
        self.event(status, activity=a.name, **({'why': why} if why else {}))
        self.activity = None
        self.c.motor.stop()
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
        """The best ground of its map by the career, from where it stands."""
        c, p = self.c, self.player
        self.repick = False
        manager = c.manager
        grounds = manager.grounds.get(p.map_id, {})
        fights = self.fights = career.fights_for(c.server, p, {t for g in grounds.values() for t in g.counts},
                                                 self.personality.risk)
        self.deadly, self.deadly_map = career.deadly_cells(grounds, fights), p.map_id
        self.keep_out()
        here = manager.flows.from_tile(p.map_id, p.x, p.y, self.blocked)
        avoid = {k for k, until in self.avoid.items() if until > now}
        players = [o.player for o in c.view if not isinstance(o, (Monster, GroundItem)) and o.player is not None]
        ranked = career.rank(
            c.server, p, grounds, travel=lambda g: here.distance(*g.center), risk=self.personality.risk,
            rng=self.rng, others=lambda g: sum(g.contains(o.map_id, o.x, o.y) for o in players), avoid=avoid,
            fights=fights)
        if not ranked:
            self.ground, self.band = None, ()
            self.event('no ground')
            return
        value, self.ground, self.band = ranked[0]
        stored = next((r for r in ranked if r[1].key == self.stored), None)
        self.stored = None
        if stored is not None and stored[0] >= value * STAY:
            value, self.ground, self.band = stored
        self.event('ground', ground=list(self.ground.key), center=list(self.ground.center),
                   worth=round(value, 3), band=list(self.band))

    def keep_out(self):
        """The deadly cells it keeps out of from where it stands: all of them, but those around it when it stands
        next to one (it has to get out)."""
        p = self.player
        if self.deadly_map != p.map_id:
            self.deadly = frozenset()  # of another map, until the next pick
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

