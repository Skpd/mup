from mup.model.player import Player
from mup.packet.base import Base


class CharList(Base):
    def __init__(self, chars: list):
        data = bytearray([0xC1, 0, 0xF3, 0, len(chars)])

        for c in chars:
            data += self.__build_char(c)

        # item, empty - max
        # rh - 0-7 << 5 | 0-31
        # lh - 0-7 << 5 | 0-31
        # h - 0-15 << 4 | a - 0-15
        # p - 0-15 << 4 | g - 0-15
        # b - 0-15 << 4 | w - 0-3 << 2 | pet - 0-3
        # short lvl, empty - 0
        # rh | lh << 3 | h << 3 | a << 3 | p << 3 | g << 3 | b << 3 - 3ch
        # item overflow flag, 1bit each, items, rh lh, ?
        # excl flag, 1bit each, items, rh lh, ?

        super().__init__(data)
        self.length = len(self)

    def __build_char(self, p: Player):
        data = bytearray([
            p.index,  # position
            *bytearray(p.name.encode('ascii')).ljust(10, b'\0'), 0x00,
            p.level & 0xFF, (p.level >> 8) & 0xFF,  # lvl little endian
            p.role_code,  # ctl
            p.class_type,  # class,
            *[
                0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
                0, 0, 0,
                0xF8, 0,
            ]  # set
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
