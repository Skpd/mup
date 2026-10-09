import logging
from mup.packet.client import CAttack
from mup.packet.server import SAction
from mup.server import combat, summon, view
from mup.server.protocol import BaseProtocol
from mup.server.world import distance

logger = logging.getLogger(__name__)


def attack_handler(msg: CAttack, proto: BaseProtocol):
    p = proto.player
    if p is None or p.dead:
        return

    logger.debug('%s attacking cid %s with %s facing %s', p.name, msg.attacked_cid, msg.action, msg.direction)

    # the attacker animates on its own, others need the swing
    p.direction = msg.direction & 0x07
    action = SAction(cid=proto.cid, direction=p.direction, action=msg.action, target=msg.attacked_cid)
    for c in view.viewers(proto.server, proto):
        c.write(action)

    # a monster, or a player (mup.server.pk)
    attacked = combat.target_of(proto.server, proto, msg.attacked_cid)
    if attacked is None:
        return
    at = combat.where(attacked)
    if distance(p.x, p.y, at.x, at.y) > combat.reach(p):
        logger.debug('%s at %s,%s is too far from %s at %s,%s', p.name, p.x, p.y, msg.attacked_cid, at.x, at.y)
        return
    if not combat.paced(p, proto.server.now, p.values.attack_speed):
        logger.info('%s attacks faster than its speed %s allows', p.name, p.values.attack_speed)
        return
    summon.owner_attacks(proto, attacked)
    combat.player_attack(proto.server, proto, attacked)
