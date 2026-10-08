from mup.packet.base import Packet, C1, u8


class AddPoint(Packet):
    """C1 F3 06: one level up point into a stat, sent while the hero has points."""
    code = C1, 0xF3, 0x06
    size = 5
    fields = (
        (4, 'stat', u8),  # 0 strength, 1 agility, 2 vitality, 3 energy
    )
