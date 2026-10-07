import random
from mup.model.monster import Monster
from mup.packet.client import CAttack
from mup.packet.server import SAction
from mup.server.combat import hit_monster
from mup.server.protocol import BaseProtocol


def attack_handler(msg: CAttack, proto: BaseProtocol):
    p = proto.player
    if p is None:
        return

    print('*** {} attacking cID {} with {} facing {}'.format(
        p.name, msg.attacked_cid, msg.action, msg.direction
    ))

    # todo check legit
    # todo pvp

    # the attacker animates on its own, others need the swing
    p.direction = msg.direction & 0x07
    action = SAction(proto.cid, p.direction, msg.action, msg.attacked_cid)
    for c in proto.server.get_players_within(p.map_id, p.x, p.y):
        if c != proto:
            c.write(action)

    attacked = proto.server.connections.get(msg.attacked_cid)
    if not isinstance(attacked, Monster) or attacked.dead:
        return

    dmg = 10 + p.level
    dmg_type = 0

    if random.randint(0, 1) > 0:
        dmg_type = 2
        dmg = int(dmg * 1.3)

    hit_monster(proto, attacked, dmg, dmg_type)
