from mup.packet.base import Base


class Move(Base):
    x = None
    y = None
    path = None

    @property
    def key(self):
        return self[2], None

    def __init__(self, src):
        super().__init__(src)

        self.x = self[3]
        self.y = self[4]
        self.path = self[5:]
