from mup.packet.base import Base


class Move(Base):
    def __init__(self, cid, x, y, direction):
        super().__init__(bytearray([0xC1, 0x08, 0x10, cid >> 8, cid & 0xFF, x, y, direction]))
