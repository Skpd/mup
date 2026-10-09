import logging
from mup.packet.client import CClientClose
from mup.server.session import Session

logger = logging.getLogger(__name__)


def close_handler(msg: CClientClose, proto: Session):
    logger.warning('Client %s reports %s: %s', proto.cid, msg.reason, msg.reasons.get(msg.reason, 'unknown'))
