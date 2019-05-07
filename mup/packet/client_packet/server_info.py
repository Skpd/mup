from mup.packet.base import Base


class ServerInfo(Base):
    server_code = None
    server_group = None

    def __init__(self, src):
        super().__init__(src)

        self.server_code = self[4] % 20
        self.server_group = int(self[4] / 20)
