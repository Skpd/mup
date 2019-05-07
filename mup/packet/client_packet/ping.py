from mup.packet.base import Base


class Ping(Base):
    tick = None
    pAttackSpeed = None
    mAttackSpeed = None

    def __init__(self, src):
        super().__init__(src)

        self.tick = int().from_bytes(src[4:8], 'little')
        self.pAttackSpeed = int().from_bytes(src[8:12], 'little')
        self.mAttackSpeed = int().from_bytes(src[12:16], 'little')
        print(src[16:], int().from_bytes(src[16:], 'little'))
