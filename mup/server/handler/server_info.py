from mup.packet.client import CServerInfo
from mup.packet.server import SServerInfo
from mup.server.protocol import BaseProtocol


def server_info_handler(msg: CServerInfo, proto: BaseProtocol):
    print('got server list message for server {} {}, gotta send information about server'.format(
        msg.server_group, msg.server_code)
    )

    selected_server = None
    for s in proto.server.available_servers:
        if s['code'] == msg.server_code and s['group'] == msg.server_group:
            selected_server = s
            break

    if selected_server is None:
        print('Server not found')
        proto.disconnect()
        return

    proto.write(SServerInfo(selected_server))
