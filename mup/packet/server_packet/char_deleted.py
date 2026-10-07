from mup.packet.base import Packet, C1, u8


class CharDeleted(Packet):
    """C1 F3 02: result 1 ok, anything else is shown as an error code."""
    code = C1, 0xF3, 0x02
    size = 5
    fields = (
        (4, 'result', u8),
    )
