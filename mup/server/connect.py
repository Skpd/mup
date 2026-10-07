from mup.config import Config
from mup.packet.server import SHandshake
from mup.server.base import ServerBase


class ConnectServer(ServerBase):
    available_servers = None

    def __init__(self, config: Config):
        super().__init__()

        self.available_servers = [
            {'code': 0, 'group': 0, 'load': 50, 'ip': config.gs_host, 'port': config.gs_port},
        ]

    def add_connection(self, c):
        super().add_connection(c)
        c.write(SHandshake())
