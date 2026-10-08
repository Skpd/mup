import logging
from mup.packet.client import CMagicAttack, CMagicAOE
from mup.packet.server import SMagic, SMagicAOE, SDamage
from mup.server import view
from mup.server.combat import hit_monster
from mup.server.protocol import BaseProtocol

logger = logging.getLogger(__name__)


def magic_attack_handler(msg: CMagicAttack, proto: BaseProtocol):
    p = proto.player
    if p is None or p.dead:
        return

    skill = p.skill(msg.skill_index)
    logger.debug('magic #%s (list index %s) from %s to %s', skill, msg.skill_index, proto.cid, msg.target_cid)

    if skill is None:
        return

    # todo pvp
    target = proto.server.monsters.get(msg.target_cid)
    ok = target is not None and not target.dead and target in proto.view

    # everyone near gets the animation, the caster too
    animation = SMagic.of(skill, proto.cid, msg.target_cid, ok)
    proto.write(animation)
    for c in view.viewers(proto.server, proto):
        c.write(animation)

    if ok:
        hit_monster(proto, target, 15, SDamage.EXCELLENT)


def aoe_magic_handler(msg: CMagicAOE, proto: BaseProtocol):
    p = proto.player
    if p is None or p.dead:
        return

    skill = p.skill(msg.skill_index)
    logger.debug('area magic #%s (list index %s) from %s at %s:%s', skill, msg.skill_index, proto.cid, msg.x, msg.y)

    if skill is None:
        return

    animation = SMagicAOE(skill=skill, caster=proto.cid, x=msg.x, y=msg.y)
    proto.write(animation)
    for c in view.viewers(proto.server, proto):
        c.write(animation)

    # todo the client reports what the skill hit with 0x1D, until then hit everything around the target point
    for m in proto.server.maps[p.map_id].monsters.near(msg.x, msg.y, 5):
        if m in proto.view:
            hit_monster(proto, m, 20)
