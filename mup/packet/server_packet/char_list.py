from mup.common.helpers import str2b
from mup.model.player import Player
from mup.packet.base import Base
from mup.packet.server_packet.appearance import appearance


class CharList(Base):
    def __init__(self, chars: list):
        data = bytearray([0xC1, 0, 0xF3, 0, len(chars)])

        for c in chars:
            data += self.__build_char(c)

        super().__init__(data)
        self.length = len(self)

    def __build_char(self, p: Player):
        data = bytearray([
            p.index,  # position
            *str2b(p.name),
            0x00,  # unk
            p.level & 0xFF, (p.level >> 8) & 0xFF,  # lvl little endian
            p.role_code,  # ctl
            *appearance(p),
        ])

        return data

    def __to_short_level(self, n):
        if n in {0, 1, 2}:
            return 0
        elif n in {3, 4}:
            return 1
        elif n in {5, 6}:
            return 2
        else:
            return n - 4
