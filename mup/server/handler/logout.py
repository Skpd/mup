import logging
from mup.packet.client import CLogout
from mup.packet.server import SLogoutResult
from mup.server.protocol import BaseProtocol

logger = logging.getLogger(__name__)


def logout_handler(msg: CLogout, proto: BaseProtocol):
    if proto.acc is None:
        return

    if msg.type not in (SLogoutResult.CLOSE, SLogoutResult.CHARACTER_SELECT, SLogoutResult.SERVER_SELECT):
        logger.warning('%s: unknown logout type %s', proto.acc.name, msg.type)
        return

    logger.info('%s logs out, type %s', proto.acc.name, msg.type)
    if proto.player is not None:
        proto.left = proto.player  # going to the server list the client sends its key settings after this
        proto.server.leave_world(proto)
    # closing the connection is up to the client, it does for types 0 and 2
    proto.write(SLogoutResult(type=msg.type))
