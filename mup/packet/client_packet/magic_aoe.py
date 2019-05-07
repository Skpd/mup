from mup.packet.base import Base


class MagicAOE(Base):
    magic_id: int
    x: int
    y: int
    direction: int

    @property
    def key(self):
        return self[2], None

    def __init__(self, src):
        super().__init__(src)
        self.magic_id = self[3]
        # self.target_cid = self[4] << 8 | self[5]
        self.x = self[4]
        self.y = self[5]
        self.direction = self[6]

        # self.distance = self[6]
        # self.x = self[7]
        # self.y = self[8]
