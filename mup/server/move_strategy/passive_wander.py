import random
from mup.model.monster import Monster
from mup.server.game import GameServer
from mup.server.protocol import BaseProtocol
from mup.packet.server import SMove, SMeetMonster


def move(me: Monster, server: GameServer):
    # 50% chance to move per interval
    if random.randint(0, 100) < 50:
        return

    # move in random direction for 0-2 steps
    cur_pos = (me.x, me.y)
    new_pos = (me.x + random.randint(-2, 2), me.y + random.randint(-2, 2))

    for c in server.get_all_within_distance(*cur_pos):
        if isinstance(c, BaseProtocol):
            c.write(SMeetMonster(me, tx=new_pos[0], ty=new_pos[1]))
            c.write(SMove(me.cid, *new_pos, 0))

    me.x = new_pos[0]
    me.y = new_pos[1]

    # # update vp if changed
    # if new_vp != cur_vp:
    #
    #     # del from current vp
    #     for vp in cur_vp:
    #         if me.cid in vp:
    #             del vp[me.cid]
    #         for _, c in vp.items():
    #             if isinstance(c, BaseProtocol):
    #                 c.write(SClear(me.cid))
    #
    #     # add to new vp
    #     for vp in new_vp:
    #         for _, c in vp.items():
    #             if isinstance(c, BaseProtocol):
    #                 # todo if tx ty is not working - send in new vp too
    #                 c.write(SMeetMonster(me, tx=new_pos[0], ty=new_pos[1]))
    #     server.get_my_viewport(0, *new_pos)[me.cid] = me
    #
    # # update object
    # me.x = new_pos[0]
    # me.y = new_pos[1]
    #
    # # send move in current vp
    # for vp in cur_vp:
    #     for _, c in vp.items():
    #         if isinstance(c, BaseProtocol):
    #             c.write(SMove(me.cid, me.x, me.y, 0))
