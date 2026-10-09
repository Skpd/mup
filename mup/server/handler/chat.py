import logging
from mup.packet.client import CChat, CWhisper
from mup.server import chat, command
from mup.server.session import Session

logger = logging.getLogger(__name__)


def chat_handler(msg: CChat, proto: Session):
    if proto.player is None:
        return
    if command.is_command(proto, msg.message):
        command.run(proto.server, proto, msg.message)
        return
    chat.say(proto.server, proto, msg.message)


def whisper_handler(msg: CWhisper, proto: Session):
    if proto.player is None:
        return
    chat.whisper(proto.server, proto, msg.name, msg.message)
