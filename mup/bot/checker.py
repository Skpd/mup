"""
Fair play: what a bot sends, checked for what the server doesn't check but a client would never do (errors: the bot
breaks the client's rules), and what the server did with it (refusals: the bot's idea of the rules is wrong). Both
are counted on the session (counts 'errors', 'refused'), errors are logged and kept for the tests.
"""
import logging
from mup.bot import motor
from mup.packet.client import CAddPoint, CAttack, CMagicAttack, CMove, CMoveGate

logger = logging.getLogger(__name__)

EARLY = 1e-6  # float slack on the walk's end


class Checker:
    def __init__(self, c):
        self.c = c
        self.walk_ends_at = 0.0
        self.errors = []  # messages

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
