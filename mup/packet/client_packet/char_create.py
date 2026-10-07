from mup.packet.base import Packet, C1, str10, u8


class CharCreate(Packet):
    """C1 F3 01"""
    code = C1, 0xF3, 0x01
    size = 15
    fields = (
        (4, 'name', str10),
        (14, 'create_class', u8),
    )

    @property
    def class_type(self):
        # client sends 0 - dw, 16 - dk, 32 - elf, 48 - mg (class number << 2),
        # everything sent back uses class number << 3, same as CharacterClass
        return self.create_class << 1
