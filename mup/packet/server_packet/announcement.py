from mup.packet.base import Base


class Announcement(Base):
    def __init__(self, message, message_type=0x00):
        assert len(message) <= 250

        super().__init__(bytearray([0xC1, 0, 0x0D, message_type, *bytearray(message, 'ascii'), 0]))
        self.length = len(self)
