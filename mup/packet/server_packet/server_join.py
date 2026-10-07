from mup.packet.base import Base


class ServerJoin(Base):
    def __init__(self, player_id, success=True, version='09704'):
        data = [0xC1, 0x00, 0xF1, 0x00, 1 if success else 0, player_id >> 8, player_id & 0xFF]
        data += [ord(x) for x in version]

        super().__init__(data)
        self.length = len(self)
