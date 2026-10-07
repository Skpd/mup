from mup.model.player import Player
from mup.packet.base import Base


class MeetPlayer(Base):
    def __init__(self, cid, p: Player):
        data = bytearray([0xC2, 0, 0, 0x12])

        data += bytearray([1])  # number of players in packet
        data += bytearray([
            cid >> 8, cid & 0xFF,
            p.x, p.y,
            p.class_type.value,  # class
            *[0x00] * 23,
            *bytearray(p.name.encode('ascii')).ljust(10, b'\0'),  # name
            p.x, p.y,  # tx ty
            0,  # path
            0, 0, 0  # unk
        ])

        data += bytearray([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])

        super().__init__(data)
        self.length = len(self)
