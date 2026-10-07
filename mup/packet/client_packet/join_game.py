from mup.packet.base import Base


class JoinGame(Base):
    name = None

    def __init__(self, src):
        super().__init__(src)
        self.name = src[4:14].strip(b'\0').decode('latin-1')
