from mup.packet.client import CDevilSquareEnter
from mup.server import devil_square
from mup.server.protocol import BaseProtocol


def devil_square_enter_handler(msg: CDevilSquareEnter, proto: BaseProtocol):
    if proto.player is None:
        return
    devil_square.enter(proto.server, proto, msg.square, msg.slot)
