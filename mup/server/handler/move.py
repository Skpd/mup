from mup.model.monster import Monster
from mup.packet.client import CMove
from mup.packet.server import SClear, SMeetMonster, SMove, SMeetPlayer
from mup.server.protocol import BaseProtocol


def move_handler(msg: CMove, proto: BaseProtocol):
    print('Move to {} {}. Path: {}'.format(msg.x, msg.y, msg.path))

    # todo check move available and legit
    # todo combine meet/clear

    p = proto.player
    # old_players = proto.server.get_players_within()
    current_vp = proto.server.get_players_within(p.x, p.y)
    new_vp = proto.server.get_players_within(msg.x, msg.y)

    p.x = msg.x
    p.y = msg.y

    if new_vp != current_vp:
        for vp in current_vp:
            if proto.cid in vp:
                del vp[proto.cid]

            for cid, c in vp.items():
                if isinstance(c, BaseProtocol):
                    if abs(msg.x - c.player.x) > proto.server.viewport_width * 2:
                        c.write(SClear(proto.cid))
                elif isinstance(c, Monster) and not c.dead:
                    if abs(msg.x - c.x) > proto.server.viewport_width * 2:
                        proto.write(SClear(c.cid))

        for vp in new_vp:
            for cid, c in vp.items():
                if isinstance(c, BaseProtocol):
                    c.write(SMeetPlayer(proto.cid, p))
                elif isinstance(c, Monster) and not c.dead:
                    proto.write(SMeetMonster(c))

        my_vp = proto.server.get_my_viewport(p.map_id, p.x, p.y)
        my_vp[proto.cid] = proto

    for vp in new_vp:
        for cid, c in vp.items():
            if isinstance(c, BaseProtocol) and cid != proto.cid:
                c.write(SMove(proto.cid, p.x, p.y, 0))

    proto.write(SMove(proto.cid, p.x, p.y, 0))
