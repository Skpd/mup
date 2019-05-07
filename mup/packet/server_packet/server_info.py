from mup.packet.base import Base


class ServerInfo(Base):
    def __init__(self, server):
        super().__init__([0xC1, 0, 0xF4, 0x03])

        ip = list(map(ord, server['ip']))
        pad = [0 for x in range(16-len(server['ip']))]
        for i in ip+pad:
            self.append(i)
        self.append(server['port'] & 0xFF)
        self.append(server['port'] >> 8 & 0xFF)

        self.length = len(self)

