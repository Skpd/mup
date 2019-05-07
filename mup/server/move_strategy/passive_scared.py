import random
from mup.model.monster import Monster
from mup.server.game import GameServer
from mup.server.protocol import BaseProtocol
from mup.packet.server import SMove, SClear, SMeetMonster


def move(me: Monster, server: GameServer):
    cur_pos = (me.x, me.y)

    # todo closest? all?
    anyone_near = False
    near_distance = []
    currently_nearby = set(server.get_players_within(*cur_pos, distance=5))
    for c in currently_nearby:
        if isinstance(c, BaseProtocol):
            anyone_near = True
            near_distance = [(me.x - c.player.x,) ,..., (me.y - c.player.y,)]
            print('Me #{} {}:{} scared of #{} {}:{}'.format(me.cid, me.x, me.y, c.cid, c.player.x, c.player.y))
            break

    if not anyone_near:
        # stay in place
        choices = [(0, ) ,..., (0, )]
    else:
        choices = near_distance

    new_pos = (max(0, me.x + random.choice(choices[0])), max(0, me.y + random.choice(choices[2])))
    new_nearby = set(server.get_players_within(*new_pos, distance=5))

    for c in (currently_nearby | new_nearby):
        c.write(SMove(me.cid, *new_pos, 0))

    for c in new_nearby - currently_nearby:
        c.write(SMeetMonster(me, *new_pos))

    for c in currently_nearby - new_nearby:
        c.write(SClear(me))

    me.x = new_pos[0]
    me.y = new_pos[1]
