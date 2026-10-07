from mup.packet.base import Packet, C1, cid


class Kill(Packet):
    """C1 17: object died. The client only reads the dying object's cid."""
    code = C1, 0x17
    size = 8
    fields = (
        (3, 'cid', cid),
        (6, 'killer', cid),
    )
