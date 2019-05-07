from mup.packet.client import CServerList
from mup.packet.server import SServerList
from mup.server.protocol import BaseProtocol


def server_list_handler(msg: CServerList, proto: BaseProtocol):
    print('got server list message, gotta send list of available servers')

    proto.write(SServerList(proto.server.available_servers))
