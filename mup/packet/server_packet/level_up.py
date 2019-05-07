from mup.common.helpers import short2b
from mup.packet.base import Base


class LevelUp(Base):
    def __init__(self, level, points, max_life, max_mana):
        super().__init__([
            0xC3, 0, 0xF3, 0x05,
            *short2b(level, False), *short2b(points, False),
            *short2b(max_life, False), *short2b(max_mana, False),
        ])
