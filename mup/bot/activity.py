"""
What a bot is doing: small state machines the brain picks by priority (mup.bot.brain). step(now) runs at every
think and returns None while it goes on, DONE or FAILED when it ended; past its timeout (if it has one) it failed.
"""
from mup.bot import career
from mup.packet.client import CAddPoint
from mup.server import ai
from mup.server.path import find_path
from mup.server.world import VIEW_RANGE, distance

DONE, FAILED = 'done', 'failed'
# priorities, lower first: survive > spend points > level
DEAD, ESCAPE, REST, POINTS, LEVEL = 0, 1, 2, 3, 4
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
        if p.life >= p.max_life * brain.personality.rest_until:
            return DONE
        threats = brain.threats(now)
        if self.c.server.maps[p.map_id].terrain.safe(p.x, p.y) or not threats:
            motor.stop()
            return None
        flee(self, threats, now)
        return None


class SpendPoints(Activity):
    """Level up points into the stats by the class build, F3 06 one at a time (the answer comes at once)."""
    name = 'points'
    priority = POINTS
    timeout = 30.0
    PER_THINK = 5

    def step(self, now):
        p = self.player
        for _ in range(self.PER_THINK):
            if p.free_points <= 0:
                return DONE
            self.c.send(CAddPoint(stat=career.next_point(p)))
        return DONE if p.free_points <= 0 else None


class Travel(Activity):
    """Walks to a hunting ground of its map down the ground's flow field around the blocked cells. Fails when it
    can't get there or stops getting closer."""
    name = 'travel'
    timeout = 1800.0
    NO_PROGRESS = 30.0  # seconds without getting closer

    def __init__(self, brain, now, ground, blocked=frozenset()):
        super().__init__(brain, now)
        self.ground = ground
        self.field = self.c.manager.flows.field(ground.map_id, ('ground',) + ground.key, lambda: ground.tiles,
                                                blocked)
        self.best = None
        self.progress_at = now

    def details(self):
        return {'to': list(self.ground.center)}

    def step(self, now):
        p, motor = self.player, self.motor
        if self.ground.contains(p.map_id, p.x, p.y):
            motor.stop()
            return DONE
        d = self.field.distance(p.x, p.y) if p.map_id == self.ground.map_id else None
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
    failed when it found nothing to kill for a long time.
    """
    name = 'hunt'
    timeout = None
    TARGET_TIME = 90.0  # seconds a target may take before it is left alone
    IDLE = 180.0  # seconds without a kill before the ground is given up
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
        self.kills = brain.kills
        self.kill_at = now
        self.unfit = False  # monsters of its band are in view but it hasn't the life to fight them

    def details(self):
        return {'ground': list(self.ground.center)}

    def step(self, now):
        brain, motor, p = self.brain, self.motor, self.player
        if brain.kills != self.kills:
            self.kills, self.kill_at = brain.kills, now
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
            motor.attack(mob, brain.skill())
            return None
        if brain.repick:
            return DONE
        if now - self.kill_at > self.IDLE:
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
