import random
from mup.model.monster import Monster
from mup.packet.client import CAttack
from mup.packet.server import SDamage, SMove, SAnnouncement, SKill, SExp, SLevelUp, SEffect
from mup.server.protocol import BaseProtocol


def attack_handler(msg: CAttack, proto: BaseProtocol):
    print('*** {} attacking cID {} with {} facing {}'.format(
        proto.player.name.decode('ascii'), msg.attacked_cid, msg.skill, msg.direction
    ))

    # todo check legit

    p = proto.player
    attacked = proto.server.connections[msg.attacked_cid]
    attacked = attacked.player if isinstance(attacked, BaseProtocol) else attacked

    if attacked.dead:
        return

    current_vp = proto.server.get_adjacent_viewports(p.map_id, p.x, p.y)

    # print('My x y: {} {}. cID {}'.format(p.x, p.y, proto.cid))
    # print('Mob x y: {} {}. cID {}'.format(attacked.x, attacked.y, attacked.cid))

    dmg = 10 + p.level
    dmg_type = 0

    if random.randint(0, 1) > 0:
        dmg_type = 2
        dmg = int(dmg * 1.3)

    dmg_message = SDamage(msg.attacked_cid, dmg, dmg_type)
    move_message = SMove(proto.cid, p.x, p.y, msg.direction)

    attacked.life -= dmg

    if attacked.life <= 0:
        attacked.dead = True

    if attacked.dead:
        # todo exp: mob.base * log(mob.level - proto.player.level, 5)
        exp = min(90, p.next_exp)
        p.exp += exp
        proto.write(SAnnouncement('{} of {}'.format(p.exp, p.next_exp)))
        proto.write(SExp(exp, msg.attacked_cid, dmg))
        if p.exp >= p.next_exp:
            p.level += 1
            p.exp = 0
            p.max_life += 10
            p.max_mana += 15
            proto.write(SLevelUp(p.level, 5, p.max_life, p.max_mana))

    for vp in current_vp:
        for cid, c in vp.items():
            # send to everyone near including self
            if isinstance(c, BaseProtocol):
                if attacked.dead:
                    c.write(SKill(attacked.cid, proto.cid))
                c.write(move_message)
                c.write(dmg_message)
