"""
Fair play: what a bot sends, checked for what the server doesn't check but a client would never do (errors: the bot
breaks the client's rules), and what the server did with it (refusals: the bot's idea of the rules is wrong). Both
are counted on the session (counts 'errors', 'refused'), errors are logged and kept for the tests. A pick up refused
because the item is another player's for a while isn't a refusal, the client can't tell (counts 'owned').

The answers it waits for count once the bot read them (received): the client sends no 22, 24, 32 or 33 before the
last one's answer, no 26 and no 24 while item use is locked (docs/protocol-097.md, Items), talks (30) from next to the
NPC, buys and sells only in the shop it talks to, repairs there only at a smith's, moves items into the vault only
while its window is open.
"""
import logging
from mup.bot import motor
from mup.packet.client import (CAddPoint, CAttack, CBuy, CDropItem, CMagicAttack, CMove, CMoveGate, CMoveItem, CPickUp,
                               CRepair, CSell, CTalk, CUseItem)
from mup.packet.server import (SBuyResult, SDurability, SItemDeleted, SLife, SMoveItemResult, SPickUpResult,
                               SSellResult, STalk)
from mup.server import inventory, shop
from mup.server.world import distance

logger = logging.getLogger(__name__)

EARLY = 1e-6  # float slack on the walk's end


class Checker:
    def __init__(self, c):
        self.c = c
        self.walk_ends_at = 0.0
        self.errors = []  # messages
        self.waiting = set()  # CPickUp, CMoveItem, CBuy, CSell: the answers it hasn't read yet
        self.locked = False  # item use, until it read the unlock

    def received(self, packets):
        """The packets the bot reads now: the answers it waited for."""
        for packet in packets:
            if isinstance(packet, SPickUpResult):
                self.waiting.discard(CPickUp)
            elif isinstance(packet, SMoveItemResult):
                self.waiting.discard(CMoveItem)
            elif isinstance(packet, SBuyResult):
                self.waiting.discard(CBuy)
            elif isinstance(packet, SSellResult):
                self.waiting.discard(CSell)
            elif isinstance(packet, SLife) and packet.type == SLife.UNLOCK \
                    or isinstance(packet, (SItemDeleted, SDurability)) and packet.unlock:
                self.locked = False

    def before(self, packet, now):
        """Checks packet before it goes to the game, returns what after() compares with."""
        p = self.c.player
        if p is None:
            return None
        if isinstance(packet, CMove):
            if (packet.x, packet.y) != (p.x, p.y):
                self.error('a walk from {},{} standing on {},{}'.format(packet.x, packet.y, p.x, p.y))
            if len(packet.steps) > CMove.MAX_STEPS:
                self.error('a walk of {} steps'.format(len(packet.steps)))
            if now < self.walk_ends_at - EARLY:
                self.error('a walk {:.2f} s before the last one ended'.format(self.walk_ends_at - now))
            self.walk_ends_at = now + len(packet.steps) * motor.STEP_TIME
            return None
        if isinstance(packet, (CAttack, CMagicAttack)):
            if now < self.walk_ends_at - EARLY:
                self.error('{} while walking'.format(type(packet).__name__))
            return p.next_attack_at
        if isinstance(packet, CMoveGate):
            return p.map_id, p.x, p.y
        if isinstance(packet, CAddPoint):
            return p.free_points
        if isinstance(packet, CPickUp):
            if CPickUp in self.waiting:
                self.error('a pick up before the last one\'s answer')
            g = self.c.server.ground.items.get(packet.id)
            if g is not None and distance(g.x, g.y, p.x, p.y) > motor.PICK_UP_REACH:
                self.error('a pick up {} tiles from the item'.format(distance(g.x, g.y, p.x, p.y)))
            if g is not None and g.item is not None and inventory.free_slot(p.inventory, g.item.info) is None:
                self.error('a pick up of {} without room for it'.format(g.item.info.name))
            return g, p.zen, dict(p.inventory)
        if isinstance(packet, CMoveItem):
            if CMoveItem in self.waiting:
                self.error('a move before the last one\'s answer')
            if self.locked:
                self.error('a move while item use is locked')
            if packet.target_window == SMoveItemResult.WAREHOUSE and not self.window(STalk.WAREHOUSE):
                self.error('a move into the vault without its window open')
            return p.inventory.get(packet.source)
        if isinstance(packet, CDropItem):
            return p.inventory.get(packet.slot)
        if isinstance(packet, CTalk):
            npc = self.c.server.monsters.get(packet.cid)
            if npc is not None and distance(npc.x, npc.y, p.x, p.y) > motor.TALK_REACH:
                self.error('a talk {} tiles from the NPC'.format(distance(npc.x, npc.y, p.x, p.y)))
            return self.c.window
        if isinstance(packet, CBuy):
            if CBuy in self.waiting:
                self.error('a buy before the last one\'s answer')
            if not self.window(STalk.SHOP):
                self.error('a buy without a shop open')
            return p.zen, dict(p.inventory)
        if isinstance(packet, CSell):
            if CSell in self.waiting:
                self.error('a sale before the last one\'s answer')
            if not self.window(STalk.SHOP):
                self.error('a sale without a shop open')
            return p.zen, dict(p.inventory)
        if isinstance(packet, CRepair):
            if not self.window(STalk.SHOP) or self.c.window.npc.type_id not in shop.REPAIRERS:
                self.error('a repair without a smith\'s shop open')
            return p.zen
        if isinstance(packet, CUseItem):
            if self.locked:
                self.error('a use while item use is locked')
            item = p.inventory.get(packet.slot)
            return item, item.durability if item is not None else None, list(p.skills)
        return None

    def after(self, packet, state, now):
        p = self.c.player
        if p is None:
            return
        if isinstance(packet, CMove):
            if (p.x, p.y) != (packet.target_x, packet.target_y):
                self.refused('the walk to {},{} stopped at {},{}'.format(packet.target_x, packet.target_y, p.x, p.y))
        elif isinstance(packet, CAttack):
            if p.next_attack_at == state:
                self.refused('a swing at {}'.format(packet.attacked_cid))
        elif isinstance(packet, CMagicAttack):
            if p.next_attack_at == state:
                self.refused('a cast of list index {} at {}'.format(packet.skill_index, packet.target_cid))
        elif isinstance(packet, CMoveGate):
            if (p.map_id, p.x, p.y) == state:
                self.refused('gate {}'.format(packet.gate))
        elif isinstance(packet, CAddPoint):
            if p.free_points == state:
                self.refused('a point into stat {}'.format(packet.stat))
        elif isinstance(packet, CPickUp):
            self.waiting.add(CPickUp)
            g, zen, before = state
            if p.zen == zen and p.inventory == before:
                if g is not None and g.owner is not None and g.owner is not self.c and now < g.owner_until:
                    self.c.counts['owned'] += 1
                else:
                    self.refused('a pick up of ground item {}'.format(packet.id))
        elif isinstance(packet, CMoveItem):
            self.waiting.add(CMoveItem)
            vault = self.c.warehouse.items if self.c.warehouse is not None else {}
            target = vault if packet.target_window == SMoveItemResult.WAREHOUSE else p.inventory
            if state is None or target.get(packet.target) is not state:
                self.refused('a move from {} to {}'.format(packet.source, packet.target))
        elif isinstance(packet, CDropItem):
            if state is None or p.inventory.get(packet.slot) is state:
                self.refused('a drop from {}'.format(packet.slot))
        elif isinstance(packet, CTalk):
            if self.c.window is None or self.c.window is state:
                self.refused('a talk to {}'.format(packet.cid))
        elif isinstance(packet, CBuy):
            self.waiting.add(CBuy)
            if (p.zen, p.inventory) == (state[0], state[1]):
                self.refused('a buy of shop slot {}'.format(packet.slot))
        elif isinstance(packet, CSell):
            self.waiting.add(CSell)
            if (p.zen, p.inventory) == (state[0], state[1]):
                self.refused('a sale of slot {}'.format(packet.slot))
        elif isinstance(packet, CRepair):
            if p.zen == state:
                self.refused('a repair of slot {}'.format(packet.slot))
        elif isinstance(packet, CUseItem):
            self.locked = True
            item, durability, skills = state
            if item is None or p.inventory.get(packet.slot) is item and item.durability == durability \
                    and p.skills == skills:
                self.refused('a use of slot {}'.format(packet.slot))

    def window(self, kind):
        """The bot talks to an NPC whose window is of kind (STalk)."""
        w = self.c.window
        return w is not None and w.kind == kind

    def error(self, message):
        c = self.c
        c.counts['errors'] += 1
        self.errors.append(message)
        logger.warning('%s breaks the client\'s rules: %s', c.bot.name, message)
        c.event('error', message=message)

    def refused(self, message):
        c = self.c
        c.counts['refused'] += 1
        logger.info('%s: the server refused %s', c.bot.name, message)
        c.event('refused', message=message)
