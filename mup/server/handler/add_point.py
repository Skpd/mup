from mup.packet.client import CAddPoint
from mup.server import stats
from mup.server.session import Session


def add_point_handler(msg: CAddPoint, proto: Session):
    if proto.player is None:
        return
    stats.add_point(proto, msg.stat)
