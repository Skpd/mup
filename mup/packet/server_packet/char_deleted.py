from mup.packet.base import Base


class CharDeleted(Base):
    def __init__(self, success: bool):
        data = [0xC1, 0, 0xF3, 0x02, 1 if success else 0]

        super().__init__(data)
        self.length = len(self)
