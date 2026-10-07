import logging
from mup.packet.client import CChat
from mup.server.protocol import BaseProtocol

logger = logging.getLogger(__name__)


def chat_handler(msg: CChat, proto: BaseProtocol):
    logger.info('Say %s: %s', msg.name, msg.message)

    proto.send_all(msg, except_self=False)
