"""
A bot's hands: what the client does for a player's clicks, at the client's pace. Walks go out in segments, the next
when the client's hero would have walked the last one; an attack order walks into reach first and swings or casts
until the target dies or leaves the view, as after a click on a monster (an area skill goes out as 1E, its effect's
1D report a moment later); a walk that ends on an entrance gate sends 1C when the level allows, the map loaded
answers F3 12. Items: a pick up order walks next to the item and sends 22; moves (24), drops (23) and uses (26) go
out at once. Like the client, one 22 and one 24 at a time until their answer, no 26 and no 24 while item use is
locked (docs/protocol-097.md, Items). Shops: a talk (30) from next to the NPC, buys (32) and sales (33) one at a
time until the answer, repairs (34, the server answers only what it did). The vault: items into its window with 24,
its close button (82).

A swing reaches as far as the client lets it (0x4650a0, code): 1.8 tiles from the middle of the hero's tile, 2.2 with
a spear in the right hand, 6 with a bow in the left or a crossbow in the right.

The client's pace, from its packets in the server logs (logs/, 2026-10-08, traffic): a knight holding the attack
swings every 0.75..0.77 s at attack speed 32 (0E); walks re-sent while walking put a tile at 0.25..0.3 s, rough. Not in
the logs: casts, potions, gates, area effects. Those are placeholders until a capture (docs/bots.md, B0 step 0).
"""
import logging
import math
from mup.model.item import GROUP_SIZE, LEFT_HAND, RIGHT_HAND
from mup.model.monster import Monster
from mup.model.player import CharacterClass
from mup.packet.client import (CAreaHits, CAttack, CBuy, CDropItem, CMagicAOE, CMagicAttack, CMapReady, CMove,
                               CMoveGate, CMoveItem, CPickUp, CRepair, CSell, CTalk, CUseItem, CWarehouseClose)
from mup.packet.server import (SBuyResult, SDropResult, SDurability, SItemDeleted, SLife, SMapMove, SMoveItemResult,
                               SPickUpResult, SRepairResult, SSellResult)
from mup.server import skill as skills
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
MELEE, SPEAR, BOW = 1.8, 2.2, 6.0  # tiles a swing reaches (client 0x4650a0), the server allows 3 and 8
SPEARS = range(3 * GROUP_SIZE, 4 * GROUP_SIZE)  # in the right hand, the client's ranges
BOWS = set(range(4 * GROUP_SIZE, 4 * GROUP_SIZE + 7)) | {4 * GROUP_SIZE + 17}  # in the left hand
CROSSBOWS = set(range(4 * GROUP_SIZE + 8, 4 * GROUP_SIZE + 15)) | {4 * GROUP_SIZE + 16}  # in the right hand
TALK_REACH = 1  # tiles: the client talks from next to the NPC, it walks there first
SWING = 0x64  # the attack animation the client sends
PICK_UP_REACH = 1  # tiles: the client sends 22 within 1.5 tiles of the item (150 units), it walks there first
USE_PAUSE = 0.5  # seconds from the unlock of an item use to the next 26, a placeholder
AREA_LAND = 0.4  # seconds from an area cast (1E) to its effect's 1D report, a placeholder
AREA_REACH = 3  # tiles around the point an effect reports targets within: the client's reach 0.8..3 tiles
AREA_TARGETS = 5  # per report, the client's limit
PICK_UP, DROP, MOVE, BUY, SELL = 'pick up', 'drop', 'move', 'buy', 'sell'  # the item requests it waits for the
# answer of


def weapon_range(p):
    """Tiles a swing of p's player reaches as the client measures them: MELEE, SPEAR or BOW by what the hands
    hold."""
    right, left = p.inventory.get(RIGHT_HAND), p.inventory.get(LEFT_HAND)
    if left is not None and left.type in BOWS or right is not None and right.type in CROSSBOWS:
        return BOW
    return SPEAR if right is not None and right.type in SPEARS else MELEE


class Motor:
    """Orders: go(path), follow(field), attack(monster, skill), pick_up(ground item), stop(); at once: move_item,
    drop, use, cast. tick(now) carries the orders out, perceive(packets, now) takes the answers."""

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
        self.item = None  # GroundItem it picks up
        self.waiting = None  # PICK_UP, DROP or MOVE: the item request it waits for the answer of
        self.locked = False  # item use: a 26 waits for its unlock
        self.use_at = 0.0  # the next 26 may go out then
        self.picked = None  # (GroundItem, picked up) of the last 22 answer, for the brain
        self.zen = 0  # its zen when the last 32, 33 or 34 went out
        self.bought = None  # the zen it paid, False: refused; the last 32 answer, for the brain
        self.sold = None  # the zen it got, False: refused; the last 33 answer, for the brain
        self.repaired = None  # the zen it paid, the last 34 answer, for the brain
        self.area = None  # (when, skill list index, x, y) of an area cast whose effect it reports
        self.serial = 0  # of the area effects it reported

    @property
    def player(self):
        return self.c.player

    def walking(self, now):
        return now < self.walk_ends_at

    def busy(self, now):
        """Walking, on an order or loading a map."""
        return self.walking(now) or bool(self.route) or self.flow is not None or self.target is not None \
            or self.item is not None or self.loading_until is not None or self.gate_sent

    def handling(self):
        """An item request waits for its answer or item use is locked: no other item request."""
        return self.waiting is not None or self.locked

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

    def pick_up(self, g):
        """Walks next to ground item g and picks it up (22), an attack order ends."""
        if self.item is not g:
            self.stop()
            self.item = g

    def move_item(self, source, target):
        """24: the item of inventory slot source to slot target (equipment below 12). False when it can't now."""
        p = self.player
        item = p.inventory.get(source)
        if item is None or self.handling():
            return False
        self.waiting = MOVE
        self.c.send(CMoveItem(source_window=SMoveItemResult.INVENTORY, source=source, item=item.encode(),
                              target_window=SMoveItemResult.INVENTORY, target=target))
        return True

    def drop(self, slot):
        """23: the item of inventory slot on its own tile. False when it can't now."""
        p = self.player
        if slot not in p.inventory or self.waiting is not None:
            return False
        self.waiting = DROP
        self.c.send(CDropItem(x=p.x, y=p.y, slot=slot))
        return True

    def use(self, slot, now):
        """26: uses the item of inventory slot (a potion, a scroll). False when item use is locked or it is too
        soon."""
        if self.locked or now < self.use_at or slot not in self.player.inventory:
            return False
        self.locked = True
        self.c.send(CUseItem(slot=slot, target=0))
        return True

    def talk(self, npc):
        """30: talks to an NPC next to it."""
        self.c.send(CTalk(cid=npc.cid))

    def buy(self, slot):
        """32: buys the goods in slot of the shop it talks to. False when an item request waits for its answer."""
        if self.waiting is not None:
            return False
        self.waiting = BUY
        self.zen = self.player.zen
        self.c.send(CBuy(slot=slot))
        return True

    def sell(self, slot):
        """33: sells the item of inventory slot to the shop it talks to (drops it on the shop's window). False when an
        item request waits for its answer."""
        if slot not in self.player.inventory or self.waiting is not None:
            return False
        self.waiting = SELL
        self.zen = self.player.zen
        self.c.send(CSell(slot=slot))
        return True

    def repair(self, slot=CRepair.ALL):
        """34: repairs the item of inventory slot, ALL everything, at the smith it talks to. The server answers what
        it did (2A, 34), nothing when it refuses."""
        self.zen = self.player.zen
        self.c.send(CRepair(slot=slot, own=0))

    def store(self, slot, target):
        """24: the item of inventory slot into slot target of the vault's window. False when it can't now."""
        item = self.player.inventory.get(slot)
        if item is None or self.handling():
            return False
        self.waiting = MOVE
        self.c.send(CMoveItem(source_window=SMoveItemResult.INVENTORY, source=slot, item=item.encode(),
                              target_window=SMoveItemResult.WAREHOUSE, target=target))
        return True

    def close_vault(self):
        """82: the vault's close button."""
        self.c.send(CWarehouseClose())

    def cast(self, number, target_cid, now):
        """19: skill number on target_cid now (a buff, a heal, a summon on itself) when its pace allows and it
        doesn't walk. False otherwise."""
        p = self.player
        info = self.c.server.skills.get(number)
        if info is None or number not in p.skills or p.mana < info.mana or self.walking(now) \
                or now < self.next_hit_at or self.loading_until is not None:
            return False
        self.c.send(CMagicAttack(skill_index=p.skills.index(number), target_cid=target_cid))
        self.next_hit_at = now + CAST_TIME / (1 + p.values.magic_speed / 100)
        return True

    def perceive(self, packets, now):
        """The answers to its requests among the packets it got."""
        for packet in packets:
            if isinstance(packet, SMapMove):
                if packet.map_change:
                    self.map_changed(now)
            elif isinstance(packet, SPickUpResult):
                if self.waiting == PICK_UP:
                    self.waiting = None
                    self.picked = self.item, packet.slot != SPickUpResult.FAILED
                    self.item = None
            elif isinstance(packet, SDropResult):
                if self.waiting == DROP:
                    self.waiting = None
            elif isinstance(packet, SMoveItemResult):
                if self.waiting == MOVE:
                    self.waiting = None
            elif isinstance(packet, SBuyResult):
                if self.waiting == BUY:
                    self.waiting = None
                    self.bought = self.zen - self.player.zen if packet.slot != SBuyResult.FAILED else False
            elif isinstance(packet, SSellResult):
                if self.waiting == SELL:
                    self.waiting = None
                    self.sold = packet.money - self.zen if packet.result else False
            elif isinstance(packet, SRepairResult):
                self.repaired = self.zen - packet.money
            elif isinstance(packet, SLife) and packet.type == SLife.UNLOCK \
                    or isinstance(packet, (SItemDeleted, SDurability)) and packet.unlock:
                if self.locked:
                    self.locked = False
                    self.use_at = now + USE_PAUSE

    def stop(self):
        self.route = []
        self.flow = None
        self.target = None
        self.skill = None
        if self.waiting != PICK_UP:
            self.item = None

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
        if self.area is not None and now >= self.area[0]:
            self._report(*self.area[1:])
            self.area = None
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
        elif self.item is not None:
            self._pick_up(now)
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

    def _pick_up(self, now):
        c, p, g = self.c, self.player, self.item
        if self.waiting == PICK_UP:
            return
        if g not in c.view:
            self.item = None
            return
        if distance(p.x, p.y, g.x, g.y) <= PICK_UP_REACH:
            if self.waiting is None:
                self.waiting = PICK_UP
                c.send(CPickUp(id=g.id))
            return
        path = find_path(c.walkable, (p.x, p.y), (g.x, g.y), reach=PICK_UP_REACH, max_steps=APPROACH_STEPS,
                         budget=APPROACH_BUDGET)
        if not path:
            self.picked = g, False
            self.item = None
            return
        self._walk(path[:SEGMENT], now)

    def weapon_range(self):
        """Tiles a swing reaches as the client measures them (weapon_range)."""
        return weapon_range(self.player)

    def walk_reach(self):
        """Tiles (a diagonal step one) from a target it walks to before it swings: all of them within the weapon's
        range."""
        return max(1, int(self.weapon_range() / math.sqrt(2)))

    def in_reach(self, mob):
        """mob is in reach: the skill's distance, the weapon's range."""
        p = self.player
        info = self.c.server.skills.get(self.skill) if self.skill is not None else None
        if info is not None:
            return distance(p.x, p.y, mob.x, mob.y) <= info.distance
        r = self.weapon_range()
        return (p.x - mob.x) ** 2 + (p.y - mob.y) ** 2 <= r * r

    def _attack(self, now):
        c, p, mob = self.c, self.player, self.target
        if mob.dead or mob not in c.view:
            self.target = None
            return
        if self.skill is not None:
            info = c.server.skills.get(self.skill)
            if info is None or p.mana < info.mana or self.skill not in p.skills:
                self.skill = None  # the client doesn't cast without the mana, the weapon then
        if self.in_reach(mob):
            if now >= self.next_hit_at:
                self._hit(mob, now)
            return
        info = c.server.skills.get(self.skill) if self.skill is not None else None
        reach = info.distance if info is not None else self.walk_reach()
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
            return
        info = c.server.skills[self.skill]
        index = p.skills.index(self.skill)
        if info.radius:
            c.send(CMagicAOE(skill_index=index, x=mob.x, y=mob.y, direction=facing))
            self.area = now + AREA_LAND, index, mob.x, mob.y
        else:
            if self.skill in skills.WEAPON_SKILLS:
                c.send(CMove.of(p.x, p.y, [], facing))  # the client turns to the target first
            c.send(CMagicAttack(skill_index=index, target_cid=mob.cid))
        if info.damage:
            self.next_hit_at = now + CAST_TIME / (1 + v.magic_speed / 100)
        else:  # weapon skills, the server paces them as swings
            self.next_hit_at = now + SWING_TIME / (1 + v.attack_speed / 100)

    def _report(self, index, x, y):
        """1D: what the effect of an area cast at x, y reached as it landed, the monsters in view around it."""
        c = self.c
        near = sorted((o for o in c.view if isinstance(o, Monster) and o.attackable and not o.dead
                       and distance(o.x, o.y, x, y) <= AREA_REACH), key=lambda o: (distance(o.x, o.y, x, y), o.cid))
        if near:
            self.serial = (self.serial + 1) & 0xFF
            c.send(CAreaHits(skill_index=index, x=x, y=y, serial=self.serial,
                             entries=[{'cid': o.cid} for o in near[:AREA_TARGETS]]))

    def _walk(self, path, now):
        p = self.player
        steps = []
        x, y = p.x, p.y
        for nx, ny in path:
            steps.append(direction(nx - x, ny - y))
            x, y = nx, ny
        self.c.send(CMove.of(p.x, p.y, steps))
        self.walk_ends_at = now + len(steps) * STEP_TIME
