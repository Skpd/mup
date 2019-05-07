from mup.packet.base import Base
from mup.packet.client import CMagicAttack, CMagicAOE
from mup.packet.server import SDamage, SMagic
from mup.server.protocol import BaseProtocol


def magic_attack_handler(msg: CMagicAttack, proto: BaseProtocol):
    print('*** magic #{} from {} to {}'.format(msg.magic_id, proto.cid, msg.target_cid))

    p = proto.player

    ok = True
    dmg = 15
    dmg_type = 1

    proto.write(SDamage(msg.target_cid, dmg, dmg_type))
    proto.write(SMagic(msg.magic_id, ok, msg.target_cid))

    for c in proto.server.get_players_within(p.x, p.y):
        if c != proto:
            c.write(SDamage(msg.target_cid, dmg, dmg_type))
            c.write(SMagic(msg.magic_id, ok, msg.target_cid, proto.cid))


def aoe_magic_handler(msg: CMagicAOE, proto: BaseProtocol):
    print('*** AOE magic #{} from {} at {}:{}'.format(msg.magic_id, proto.cid, msg.x, msg.y))

    p = proto.player

    ok = True
    dmg = 20
    dmg_type = 0

    dmg_messages = []

    for m in proto.server.get_monsters_within(msg.x, msg.y, distance=5):
        if ok:
            dmg_messages.append(SDamage(m.cid, dmg, dmg_type))

    for c in proto.server.get_players_within(p.x, p.y):
        if c != proto:
            c.write(Base(bytearray([0xC3, 0x00, 0x1E, msg.magic_id + 1, proto.cid >> 8, proto.cid & 0xff, msg.x, msg.y, msg.direction])))
        else:
            c.write(Base(bytearray([0xC3, 0x00, 0x1E, msg.magic_id + 1, 0, 0, msg.x, msg.y, msg.direction])))

        for dmg_msg in dmg_messages:
            c.write(dmg_msg)
