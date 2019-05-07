from mup.packet.base import Base


class Chat(Base):
    message = None
    name = None

    @property
    def key(self):
        return self[2], None

    def __init__(self, src):
        super().__init__(src)

        self.name = src[3:13].decode().strip('\0')
        self.message = src[13:].decode().strip('\0')
