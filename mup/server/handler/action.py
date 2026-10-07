from mup.packet.client import CRotate
from mup.packet.server import SAction
from mup.server.protocol import BaseProtocol


def action_handler(msg: CRotate, proto: BaseProtocol):
    p = proto.player
    if p is None:
        return

    p.direction = msg.direction & 0x07

    action = SAction(cid=proto.cid, direction=p.direction, action=msg.action)
    for c in proto.server.get_players_within(p.map_id, p.x, p.y):
        if c != proto:
            c.write(action)
