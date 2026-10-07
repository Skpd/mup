from mup.packet.base import Base


class CharCreate(Base):
    name = None
    class_type = None

    def __init__(self, src):
        super().__init__(src)

        self.name = src[4:14].decode('latin-1').strip('\0')
        # client sends 0 - dw, 16 - dk, 32 - elf, 48 - mg (class number << 2),
        # everything sent back uses class number << 3, same as CharacterClass
        self.class_type = src[14] << 1
