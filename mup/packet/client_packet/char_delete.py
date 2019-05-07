from mup.packet.base import Base


class CharDelete(Base):
    name = None
    passw = None

    def __init__(self, src):
        super().__init__(src)

        self.name = src[4:14].decode().strip('\0')
        self.passw = src[14:24].decode().strip('\0')
