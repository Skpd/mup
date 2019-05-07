from mup.packet.client import CChat
from mup.server.protocol import BaseProtocol


def chat_handler(msg: CChat, proto: BaseProtocol):
    print('Say {}: {}'.format(msg.name, msg.message))

    proto.send_all(msg, except_self=False)
