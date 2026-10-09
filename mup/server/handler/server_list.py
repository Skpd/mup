from mup.packet.client import CServerList
from mup.packet.server import SServerList
from mup.server.session import Session


def server_list_handler(msg: CServerList, proto: Session):
    proto.write(SServerList.of(proto.server.available_servers))
