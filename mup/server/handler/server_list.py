from mup.packet.client import CServerList
from mup.packet.server import SServerList
from mup.server.protocol import BaseProtocol


def server_list_handler(msg: CServerList, proto: BaseProtocol):
    proto.write(SServerList.of(proto.server.available_servers))
