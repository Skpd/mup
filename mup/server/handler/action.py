from mup.packet.client import CRotate
from mup.packet.server import SAction
from mup.server import view
from mup.server.session import Session


def action_handler(msg: CRotate, proto: Session):
    p = proto.player
    if p is None or p.dead:
        return

    p.direction = msg.direction & 0x07

    action = SAction(cid=proto.cid, direction=p.direction, action=msg.action)
    for c in view.viewers(proto.server, proto):
        c.write(action)
