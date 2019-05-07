from mup.packet.base import Base


class Handshake(Base):
    def __init__(self):
        super().__init__([0xC1, 0x04, 0x00, 0x01])
