from mup.packet.base import Base


class Rotate(Base):
    direction = None
    action = None

    @property
    def sub(self):
        return None

    @property
    def key(self):
        return self[2], None

    def __init__(self, src):
        super().__init__(src)
        self.direction = src[3]
        self.action = src[4]
