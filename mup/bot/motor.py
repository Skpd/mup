"""
A bot's hands: what the client does for a player's clicks, at the client's pace. Walks go out in segments, the next
when the client's hero would have walked the last one; an attack order walks into reach first and swings or casts
until the target dies or leaves the view, as after a click on a monster; a walk that ends on an entrance gate sends
1C when the level allows, the map loaded answers F3 12.

The client's pace, from its packets in the server logs (logs/, 2026-10-08, traffic): a knight holding the attack
swings every 0.75..0.77 s at attack speed 32 (0E); walks re-sent while walking put a tile at 0.25..0.3 s, rough. Not in
the logs: casts, potions, gates. Those are placeholders until a capture (docs/bots.md, B0 step 0).
"""
import logging
from mup.model.player import CharacterClass
from mup.packet.client import CAttack, CMagicAttack, CMapReady, CMove, CMoveGate
from mup.server.path import direction, find_path
from mup.server.world import distance

logger = logging.getLogger(__name__)

STEP_TIME = 0.3  # seconds per tile walked, traffic (rough)
SWING_TIME = 1.0  # seconds per swing at attack speed 0: 0.76 s at 32 (traffic) with the server's shape of the pace
CAST_TIME = 1.0  # seconds per cast at magic speed 0, the swing's until a capture
MAP_LOAD = 1.0  # seconds from the 1C answer to F3 12, a placeholder
GATE_PAUSE = 3.0  # the client sends 1C at most every 3 s (code 0x474030)
SEGMENT = 8  # steps per walk packet
APPROACH_SEGMENT = 4  # towards a target that moves, shorter
APPROACH_STEPS = 40  # a path to a target takes at most, around a wall
APPROACH_BUDGET = 1000  # tiles looked at for it
MELEE = 1  # tiles a swing is made from: next to the target, the server allows 3
SWING = 0x64  # the attack animation the client sends


class Motor:
    """Orders: go(path), follow(field), attack(monster, skill), stop(). tick(now) carries them out."""

    def __init__(self, c):
        self.c = c
        self.route = []  # tiles still to walk
        self.flow = None  # a flow field it walks down
        self.walk_ends_at = 0.0  # the client's hero is at the end of the last walk then
        self.next_hit_at = 0.0  # its next swing or cast
        self.target = None  # the monster it attacks
        self.skill = None  # the skill number it attacks with, None: the weapon
        self.unreachable = None  # cid of a target it found no path to, for the brain
        self.loading_until = None  # the map it went to is loaded then, F3 12 goes out
        self.gate_at = 0.0  # the next 1C may go out then
        self.gate_sent = False  # a 1C waits for its answer
        self.blocked_gate = None  # number of a gate it stands on without the level

    @property
    def player(self):
        return self.c.player

    def walking(self, now):
        return now < self.walk_ends_at

    def busy(self, now):
        """Walking, on an order or loading a map."""
        return self.walking(now) or bool(self.route) or self.flow is not None or self.target is not None \
            or self.loading_until is not None or self.gate_sent

    def go(self, path):
        """Walks the tiles of path (from the next one on), an attack order ends."""
        self.stop()
        self.route = list(path)

    def follow(self, field):
        """Walks down field until its target area, an attack order ends."""
        self.stop()
        self.flow = field

    def attack(self, mob, skill=None):
        """Attacks mob with skill (a number) or the weapon until it dies or leaves the view."""
        if self.target is not mob:
            self.stop()
            self.target = mob
        self.skill = skill
        self.unreachable = None

    def stop(self):
        self.route = []
        self.flow = None
        self.target = None
        self.skill = None

    def map_changed(self, now):
        """The 1C answer to its gate request (or a GM move): the client loads the map."""
        self.stop()
        self.gate_sent = False
        self.walk_ends_at = now
        self.loading_until = now + MAP_LOAD

    def tick(self, now):
        c, p = self.c, self.player
        if p is None or p.dead:
            return
        if self.loading_until is not None:
            if now < self.loading_until:
                return
            self.loading_until = None
            c.send(CMapReady())
        if self.gate_sent and now >= self.gate_at:
            self.gate_sent = False  # no answer, the server refused it
        if self.walking(now) or self.gate_sent:
            return
        if self.on_gate(now):
            return
        if self.target is not None:
            self._attack(now)
        elif self.route:
            self._walk(self.route[:SEGMENT], now)
            del self.route[:SEGMENT]
        elif self.flow is not None:
            path = self.flow.path(p.x, p.y, SEGMENT)
            if path:
                self._walk(path, now)
            else:
                self.flow = None

    def on_gate(self, now):
        """Standing on an entrance gate: 1C when the level allows, as the client does. True when it went out."""
        p = self.player
        g = next((g for g in self.c.manager.flows.entrances(p.map_id) if g.contains(p.map_id, p.x, p.y)), None)
        self.blocked_gate = None
        if g is None or now < self.gate_at:
            return False
        if p.level < g.min_level(p.class_type.base == CharacterClass.MAGIC_GLADIATOR):
            self.blocked_gate = g.number
            return False
        self.stop()
        self.gate_at = now + GATE_PAUSE
        self.gate_sent = True
        self.c.send(CMoveGate(gate=g.number, x=0, y=0))
        return True

    def reach(self):
        """Tiles from the target it hits from: the skill's distance, next to it with the weapon."""
        info = self.c.server.skills.get(self.skill) if self.skill is not None else None
        return info.distance if info is not None else MELEE

    def _attack(self, now):
        c, p, mob = self.c, self.player, self.target
        if mob.dead or mob not in c.view:
            self.target = None
            return
        if self.skill is not None:
            info = c.server.skills.get(self.skill)
            if info is None or p.mana < info.mana or self.skill not in p.skills:
                self.skill = None  # the client doesn't cast without the mana, the weapon then
        reach = self.reach()
        if distance(p.x, p.y, mob.x, mob.y) <= reach:
            if now >= self.next_hit_at:
                self._hit(mob, now)
            return
        path = find_path(c.walkable, (p.x, p.y), (mob.x, mob.y), reach=reach, max_steps=APPROACH_STEPS,
                         budget=APPROACH_BUDGET)
        if not path:
            self.unreachable = mob.cid
            self.target = None
            return
        self._walk(path[:APPROACH_SEGMENT], now)

    def _hit(self, mob, now):
        c, p = self.c, self.player
        v = p.values
        facing = direction(mob.x - p.x, mob.y - p.y) or 0
        if self.skill is None:
            c.send(CAttack(attacked_cid=mob.cid, action=SWING, direction=facing))
            self.next_hit_at = now + SWING_TIME / (1 + v.attack_speed / 100)
        else:
            c.send(CMagicAttack(skill_index=p.skills.index(self.skill), target_cid=mob.cid))
            self.next_hit_at = now + CAST_TIME / (1 + v.magic_speed / 100)

    def _walk(self, path, now):
        p = self.player
        steps = []
        x, y = p.x, p.y
        for nx, ny in path:
            steps.append(direction(nx - x, ny - y))
            x, y = nx, ny
        self.c.send(CMove.of(p.x, p.y, steps))
        self.walk_ends_at = now + len(steps) * STEP_TIME
