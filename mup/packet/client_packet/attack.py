from mup.packet.base import Base


class Attack(Base):
    attacked_cid = None
    action = None
    direction = None

    @property
    def key(self):
        return self[2], None

    def __init__(self, src):
        super().__init__(src)

        self.attacked_cid = self[3] << 8 | self[4]
        self.action = self[5]  # attack animation, sent to others in the action packet
        self.direction = self[6]
