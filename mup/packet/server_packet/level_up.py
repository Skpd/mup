from mup.packet.base import Packet, C1, C3, u8, u16


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


class PointResult(Packet):
    """C1 F3 06: [4] high nibble 0: refused, otherwise the low nibble is the stat, the client takes a point and adds 1
    to it. Vitality: the new max life in [6..7], energy: the new max mana."""
    code = C1, 0xF3, 0x06
    size = 8
    fields = (
        (4, 'result', u8),
        (6, 'value', u16, 0),
    )

    OK = 0x10
