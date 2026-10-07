from mup.packet.base import Packet, C1, cid, u16be


class Damage(Packet):
    """C1 15: damage number over the target, 0 shows a miss."""
    code = C1, 0x15
    size = 7
    fields = (
        (3, 'cid', cid),
        (5, 'damage', u16be),  # value in the low 13 bits, colour flags in the top 3
    )

    MAX = 0x1FFF
    # colours, excellent wins over critical over magenta. None: orange, red when the target is you
    EXCELLENT = 0x4000  # green
    CRITICAL = 0x8000  # blue
    MAGENTA = 0x2000

    @classmethod
    def of(cls, target, damage, flags=0):
        return cls(cid=target, damage=max(0, min(damage, cls.MAX)) | flags)
