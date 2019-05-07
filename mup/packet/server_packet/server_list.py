from mup.packet.base import Base


class ServerList(Base):
    def __init__(self, servers: list):
        data = [0xC2, 0, 0, 0xF4, 0x02, len(servers)]

        for n, s in enumerate(servers):
            data.append(s['group'] * 20 + s['code'])
            data.append(0)

            data.append(s['load'])
            data.append(0)

        super().__init__(data)
        self.length = len(data)
