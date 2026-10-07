import os

from mup.packet.server import SHandshake
from mup.server.base import ServerBase


class ConnectServer(ServerBase):
    available_servers = None

    def __init__(self):
        super().__init__()

        # address the client connects to for the game server, 172.17.0.1 for a client in docker
        gs_host = os.environ.get('MU_GS_HOST', '127.0.0.1')

        self.available_servers = [
            {'code': 0, 'group': 0, 'load': 50, 'ip': gs_host, 'port': 55901},
        ]

    def add_connection(self, c):
        super().add_connection(c)
        print('added connection', c)
        c.write(SHandshake())
