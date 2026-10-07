from mup.common.helpers import str2b
from mup.model.player import Player
from mup.packet.base import Base


class CharCreated(Base):
    def __init__(self, p: Player = None):
        if p is None:
            data = [0xC1, 0, 0xF3, 0x01, 0]
        else:
            data = [
                0xC1, 0, 0xF3, 0x01, 1,
                *str2b(p.name),
                p.index,  # position
                p.level & 0xFF, (p.level >> 8) & 0xFF,  # lvl little endian
                p.class_type.value,
            ]

        super().__init__(data)
        self.length = len(self)
