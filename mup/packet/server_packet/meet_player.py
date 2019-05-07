from mup.model.player import Player
from mup.packet.base import Base


class MeetPlayer(Base):
    def __init__(self, cid, p: Player):
        data = bytearray([0xC2, 0, 0, 0x12])

        data += bytearray([1])  # number of players in packet
        data += bytearray([
            cid >> 8, cid & 0xFF,
            p.x, p.y,
            p.class_type,  # class class << 5 | skin << 4 | pose
            *[
                0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
                0, 0, 0,
                0xF8, 0,
            ],
            0,
            p.state,  # state
            p.role_code,
            *bytearray(p.name).ljust(10, b'\0'),  # name
            p.x, p.y,  # tx ty
            0 << 4 | p.pk  # direction << 4 | pk status
        ])

        super().__init__(data)
        self.length = len(self)
