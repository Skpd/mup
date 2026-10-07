from mup.packet.base import Base


class MagicAttack(Base):
    skill_index: int  # position in the skill list sent on join, not the skill number
    target_cid: int

    @property
    def key(self):
        return self[2], None

    def __init__(self, src):
        super().__init__(src)
        self.skill_index = self[3]
        self.target_cid = self[4] << 8 | self[5]
