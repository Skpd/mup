from mup.packet.base import Packet, C1, cid, u8


class Place(Packet):
    """C1 11: puts an object on x, y without walking (a teleport seen by others)."""
    code = C1, 0x11
    size = 7
    fields = (
        (3, 'cid', cid),
        (5, 'x', u8),
        (6, 'y', u8),
    )
