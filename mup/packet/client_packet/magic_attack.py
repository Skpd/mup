from mup.packet.base import Base


class MagicAttack(Base):
    magic_id: int
    target_cid: int

    @property
    def key(self):
        return self[2], None

    def __init__(self, src):
        super().__init__(src)
        self.magic_id = self[3]
        self.target_cid = self[4] << 8 | self[5]
