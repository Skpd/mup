import logging
from mup.packet.client import CMove
from mup.packet.server import SClear, SMeetMonster, SMove, SMeetPlayer
from mup.server.protocol import BaseProtocol

logger = logging.getLogger(__name__)


def move_handler(msg: CMove, proto: BaseProtocol):
    logger.debug('Move from %s %s to %s %s. Path: %s', msg.x, msg.y, msg.target_x, msg.target_y, msg.path.hex())

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
        c.write(SClear.of([proto.cid]))
        proto.write(SClear.of([c.cid]))

    for c in new_players - old_players:
        c.write(SMeetPlayer.of([(proto.cid, p)]))
        proto.write(SMeetPlayer.of([(c.cid, c.player)]))

    for m in old_monsters - new_monsters:
        proto.write(SClear.of([m.cid]))

    for m in new_monsters - old_monsters:
        proto.write(SMeetMonster.of([m]))

    # the mover walks on its own, others only need the target
    move = SMove(cid=proto.cid, x=p.x, y=p.y, direction=p.direction << 4)
    for c in old_players & new_players:
        c.write(move)
