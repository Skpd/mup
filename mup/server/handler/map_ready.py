import logging
from mup.packet.client import CMapReady
from mup.server.protocol import BaseProtocol

logger = logging.getLogger(__name__)


def map_ready_handler(msg: CMapReady, proto: BaseProtocol):
    # the objects in view went out with the map change already
    logger.debug('%s loaded the map', proto.cid)
