from mup.packet.base import Packet, C3, u16


class LevelUp(Packet):
    """C3 F3 05"""
    code = C3, 0xF3, 0x05
    size = 12
    fields = (
        (4, 'level', u16),
        (6, 'points', u16),
        (8, 'max_life', u16),
        (10, 'max_mana', u16),
    )
