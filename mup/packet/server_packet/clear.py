from mup.packet.base import Base


class Clear(Base):
    def __init__(self, cid):
        super().__init__(bytearray([0xC1, 6, 0x14, 1, cid >> 8, cid & 0xff]))
