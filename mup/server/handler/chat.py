import logging
from mup.packet.client import CChat
from mup.server import command
from mup.server.protocol import BaseProtocol

logger = logging.getLogger(__name__)


def chat_handler(msg: CChat, proto: BaseProtocol):
    if proto.player is not None and command.is_command(proto, msg.message):
        command.run(proto.server, proto, msg.message)
        return

    logger.info('Say %s: %s', msg.name, msg.message)
    proto.send_all(msg, except_self=False)
