from mup.packet.base import Base


class CharCreate(Base):
    name = None
    class_type = None

    def __init__(self, src):
        super().__init__(src)

        self.name = src[4:14].decode('ascii').strip('\0')
        # 0 - dw, 32 - dk, 64 - ee, 96 - mg, 128 - sm, 160 - bk, 192 - me
        self.class_type = src[14]
