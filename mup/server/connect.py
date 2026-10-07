from random import randint

from mup.packet.server import SHandshake
from mup.server.base import ServerBase


class ConnectServer(ServerBase):
    available_servers = None

    def __init__(self):
        super().__init__()

        self.available_servers = [
            {'code': 1, 'group': 4, 'load': randint(0, 100), 'ip': '172.17.0.1', 'port': 55901},
            {'code': 2, 'group': 4, 'load': randint(0, 100), 'ip': '127.0.0.1', 'port': 55901},
            {'code': 3, 'group': 4, 'load': randint(0, 100), 'ip': '172.17.0.2', 'port': 55901},
            {'code': 4, 'group': 4, 'load': randint(0, 100), 'ip': '10.0.2.15', 'port': 55901},
        ]

    def add_connection(self, c):
        super().add_connection(c)
        print('added connection', c)
        c.write(SHandshake())
