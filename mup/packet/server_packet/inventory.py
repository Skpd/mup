from mup.packet.base import Base


class Inventory(Base):
    def __init__(self, items):
        data = [0xC4, 0, 0, 0xF3, 0x10, 0x00]

        super().__init__(data)
        self.length = len(self)
