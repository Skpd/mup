from mup.packet.client import CAddPoint
from mup.server import stats
from mup.server.protocol import BaseProtocol


def add_point_handler(msg: CAddPoint, proto: BaseProtocol):
    if proto.player is None:
        return
    stats.add_point(proto, msg.stat)
