from mup.model.monster import Monster
from mup.packet.base import Base
from mup.packet.client import CMagicAttack, CMagicAOE
from mup.packet.server import SMagic
from mup.server.combat import hit_monster
from mup.server.protocol import BaseProtocol


def magic_attack_handler(msg: CMagicAttack, proto: BaseProtocol):
    p = proto.player
    if p is None:
        return

    skill = p.skill(msg.skill_index)
    print('*** magic #{} (list index {}) from {} to {}'.format(skill, msg.skill_index, proto.cid, msg.target_cid))

    if skill is None:
        return

    # todo pvp
    target = proto.server.connections.get(msg.target_cid)
    ok = isinstance(target, Monster) and not target.dead

    # everyone near gets the animation, the caster too
    animation = SMagic(skill, ok, msg.target_cid, proto.cid)
    for c in proto.server.get_players_within(p.map_id, p.x, p.y):
        c.write(animation)

    if ok:
        hit_monster(proto, target, 15, 1)


def aoe_magic_handler(msg: CMagicAOE, proto: BaseProtocol):
    p = proto.player
    if p is None:
        return

    skill = p.skill(msg.skill_index)
    print('*** AOE magic #{} (list index {}) from {} at {}:{}'.format(skill, msg.skill_index, proto.cid, msg.x, msg.y))

    if skill is None:
        return

    animation = Base(bytearray([0xC3, 0x00, 0x1E, skill, proto.cid >> 8, proto.cid & 0xff, msg.x, msg.y, msg.direction]))
    for c in proto.server.get_players_within(p.map_id, p.x, p.y):
        c.write(animation)

    # todo the client reports what the skill hit with 0x1D, until then hit everything around the target point
    for m in proto.server.get_monsters_within(p.map_id, msg.x, msg.y, distance=5):
        hit_monster(proto, m, 20, 0)
