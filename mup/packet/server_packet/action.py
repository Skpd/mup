from mup.packet.base import Packet, C1, cid, u8


class Action(Packet):
    """C1 18: object animation: rotation, emotes, attacks."""
    code = C1, 0x18
    size = 9
    fields = (
        (3, 'cid', cid),
        (5, 'direction', u8),
        (6, 'action', u8),
        (7, 'target', cid, 0),
    )
