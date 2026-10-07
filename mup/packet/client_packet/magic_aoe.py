from mup.packet.base import Base


class MagicAOE(Base):
    skill_index: int  # position in the skill list sent on join, not the skill number
    x: int
    y: int
    direction: int

    @property
    def key(self):
        return self[2], None

    def __init__(self, src):
        super().__init__(src)
        self.skill_index = self[3]
        self.x = self[4]
        self.y = self[5]
        self.direction = self[6]
