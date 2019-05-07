from mup.packet.base import Base


class Attack(Base):
    attacked_cid = None
    skill = None
    direction = None

    @property
    def key(self):
        return self[2], None

    def __init__(self, src):
        super().__init__(src)

        self.attacked_cid = self[3] << 8 | self[4]
        self.skill = self[5]
        self.direction = self[6]
