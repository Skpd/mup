from mup.packet.server import SHandshake
from mup.server.base import ServerBase


class ConnectServer(ServerBase):
    available_servers = None

    def __init__(self):
        super().__init__()

        self.available_servers = [
            {'code': 0, 'group': 0, 'load': 50, 'ip': '127.0.0.1', 'port': 55901},
        ]

    def add_connection(self, c):
        super().add_connection(c)
        print('added connection', c)
        c.write(SHandshake())
