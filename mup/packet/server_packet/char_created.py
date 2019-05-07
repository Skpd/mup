from random import randint
from mup.packet.base import Base


class CharCreated(Base):
    def __init__(self, success: bool, char, name, index=1):
        assert len(str(name)) <= 10, 'invalid account id, must be < 10 chars'

        data = [0xC1, 0, 0xF3, 0x01, 1 if success else 0, *bytearray(bytes(name, 'ascii')).ljust(10, b'\0')]
        data += [1]
        # todo items
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

        # data += [
        #     2 << 5 | 3,
        #     3 << 5 | 4,
        #     2 << 4 | 2 << 4,
        #     2 << 4 | 2 << 4,
        #     2 << 4 | 1 << 2 | 1 << 2,
        #     0xff, 0xff, 0xff,
        #     0xff,
        #     0xff,
        # ]
        super().__init__(data)
        self.length = len(self)
