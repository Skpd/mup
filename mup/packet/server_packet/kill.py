from mup.packet.base import Base


class Kill(Base):
    def __init__(self, dead_cid, killer_cid):
        super().__init__(bytearray([
            0xC1, 0x08, 0x17, dead_cid >> 8, dead_cid & 0xff, 0, killer_cid >> 8, killer_cid & 0xff
        ]))
