from mup.packet.client import CClientClose
from mup.server.protocol import BaseProtocol


def close_handler(msg: CClientClose, proto: BaseProtocol):
    print('Client close reason: {}'.format(msg.code))
    proto.disconnect()
