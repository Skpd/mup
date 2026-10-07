from mup.packet.base import Packet, C1, cid, u8


class Move(Packet):
    """C1 10: object walks to x, y."""
    code = C1, 0x10
    size = 8
    fields = (
        (3, 'cid', cid),
        (5, 'x', u8),
        (6, 'y', u8),
        (7, 'direction', u8),  # direction << 4
    )
