from time import time

from mup.packet.client import CPing
from mup.server.protocol import BaseProtocol


def ping_handler(msg: CPing, proto: BaseProtocol):
    print('Ping. Tick {} p/m aspd {} {}. '.format(msg.tick, msg.pAttackSpeed, msg.mAttackSpeed))

    next_server_tick = time() * 1000
    next_client_tick = msg.tick

    if proto.server_tick is not None and proto.client_tick is not None:
        server_diff = next_server_tick - proto.server_tick
        client_diff = next_client_tick - proto.client_tick
        ping = client_diff - server_diff
        print('Serve tick diff: {}, client tick diff {}, ping: {}'.format(server_diff, client_diff, ping))

    proto.write(bytearray([0xC1, 4, 0xE0, 0x99]))

    proto.server_tick = next_server_tick
    proto.client_tick = next_client_tick
