from mup.packet.base import Packet, C1, Raw, cid, u8


class ServerJoin(Packet):
    """C1 F1 00: the version must be the client's own (09704) or it shows "version not matched"."""
    code = C1, 0xF1, 0x00
    size = 12
    fields = (
        (4, 'result', u8, 1),
        (5, 'cid', cid),
        (7, 'version', Raw(5), b'09704'),
    )
