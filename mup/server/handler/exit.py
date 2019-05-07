from mup.packet.client import CExit
from mup.server.protocol import BaseProtocol


def exit_handler(msg: CExit, proto: BaseProtocol):
    print('Client exit.')
    proto.disconnect()
