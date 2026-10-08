import logging
from mup.packet.client import CMagicAttack, CMagicAOE, CAreaHits
from mup.server import casting
from mup.server.protocol import BaseProtocol

logger = logging.getLogger(__name__)


def magic_attack_handler(msg: CMagicAttack, proto: BaseProtocol):
    if proto.player is None:
        return
    logger.debug('%s: skill list index %s on %s', proto.player.name, msg.skill_index, msg.target_cid)
    casting.on_target(proto.server, proto, msg.skill_index, msg.target_cid)


def aoe_magic_handler(msg: CMagicAOE, proto: BaseProtocol):
    if proto.player is None:
        return
    logger.debug('%s: area skill list index %s at %s,%s', proto.player.name, msg.skill_index, msg.x, msg.y)
    casting.on_area(proto.server, proto, msg.skill_index, msg.x, msg.y, msg.direction)


def area_hits_handler(msg: CAreaHits, proto: BaseProtocol):
    if proto.player is None:
        return
    cids = [e['cid'] for e in msg.entries]
    logger.debug('%s: area skill list index %s landed at %s,%s (%s), hits %s', proto.player.name, msg.skill_index,
                 msg.x, msg.y, msg.serial, cids)
    casting.area_hits(proto.server, proto, msg.skill_index, msg.x, msg.y, msg.serial, cids)
