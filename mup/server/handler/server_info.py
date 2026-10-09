import logging
from mup.packet.client import CServerInfo
from mup.packet.server import SServerInfo
from mup.server.session import Session

logger = logging.getLogger(__name__)


def server_info_handler(msg: CServerInfo, proto: Session):
    for s in proto.server.available_servers:
        if s['group'] * 20 + s['code'] == msg.server_code:
            proto.write(SServerInfo(ip=s['ip'], port=s['port']))
            return

    logger.warning('Server %s not found', msg.server_code)
    proto.disconnect()
