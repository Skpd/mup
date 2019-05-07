import random

from mup.model.monster import Monster
from mup.packet.base import Base


class MeetMonster(Base):
    def __init__(self, monster: Monster, tx=None, ty=None):
        data = bytearray([0xC2, 0, 0, 0x13])

        data += bytearray([1])  # number of monsters in packet
        data += bytearray([
            monster.cid >> 8, monster.cid & 0xFF,  # connection id b2
            monster.type_id,  # monster id b2
            0,  # unknown
            monster.state,  # view state
            0,  # unknown
            monster.x & 0xff, monster.y & 0xff,  # x y
            (monster.x if not tx else tx) & 0xff,
            (monster.y if not ty else ty) & 0xff,  # tx ty
            0,  # path
            0   # unknown
        ])

        super().__init__(data)
        self.length = len(self)
