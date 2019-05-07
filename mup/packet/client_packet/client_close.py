from mup.packet.base import Base


class ClientClose(Base):
    code = None
    code_map = {
        6: 'Encoding required'
    }

    def __init__(self, src):
        self.code = int(src[4])
        super().__init__(src)
