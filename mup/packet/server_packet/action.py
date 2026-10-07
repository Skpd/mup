from mup.packet.base import Base


class Action(Base):
    """Object animation: rotation, emotes, attacks."""
    def __init__(self, cid, direction, action, target_cid=0):
        super().__init__(bytearray([
            0xC1, 0x09, 0x18,
            cid >> 8, cid & 0xFF,
            direction, action,
            target_cid >> 8, target_cid & 0xFF,
        ]))
