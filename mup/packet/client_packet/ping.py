from mup.packet.base import Packet, C3, u16, u32


class Ping(Packet):
    """C3 0E 00"""
    code = C3, 0x0E, 0x00
    size = 12
    fields = (
        (4, 'tick', u32),  # GetTickCount
        (8, 'attack_speed', u16),
        (10, 'magic_speed', u16),
    )
