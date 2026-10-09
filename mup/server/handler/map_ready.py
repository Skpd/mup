import logging
from mup.packet.client import CMapReady
from mup.server.session import Session

logger = logging.getLogger(__name__)


def map_ready_handler(msg: CMapReady, proto: Session):
    # the objects in view went out with the map change already
    logger.debug('%s loaded the map', proto.cid)
