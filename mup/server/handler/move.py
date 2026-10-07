from mup.packet.client import CMove
from mup.packet.server import SClear, SMeetMonster, SMove, SMeetPlayer
from mup.server.protocol import BaseProtocol


def move_handler(msg: CMove, proto: BaseProtocol):
    print('Move from {} {} to {} {}. Path: {}'.format(msg.x, msg.y, msg.target_x, msg.target_y, msg.path.hex()))

    # todo check move available and legit

    p = proto.player
    if p is None:
        return

    server = proto.server
    old_players = set(server.get_players_within(p.map_id, p.x, p.y))
    old_monsters = set(server.get_monsters_within(p.map_id, p.x, p.y))

    p.x = msg.target_x
    p.y = msg.target_y
    p.direction = msg.direction

    new_players = set(server.get_players_within(p.map_id, p.x, p.y))
    new_monsters = set(server.get_monsters_within(p.map_id, p.x, p.y))
    old_players.discard(proto)
    new_players.discard(proto)

    for c in old_players - new_players:
        c.write(SClear(proto.cid))
        proto.write(SClear(c.cid))

    for c in new_players - old_players:
        c.write(SMeetPlayer(proto.cid, p))
        proto.write(SMeetPlayer(c.cid, c.player))

    for m in old_monsters - new_monsters:
        proto.write(SClear(m.cid))

    for m in new_monsters - old_monsters:
        proto.write(SMeetMonster(m))

    # the mover walks on its own, others only need the target
    move = SMove(proto.cid, p.x, p.y, p.direction << 4)
    for c in old_players & new_players:
        c.write(move)
