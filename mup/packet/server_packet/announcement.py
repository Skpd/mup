from mup.packet.base import Packet, C1, Text, u8


class Announcement(Packet):
    """C1 0D: notice."""
    code = C1, 0x0D
    fields = (
        (3, 'type', u8, 0),
        (4, 'message', Text()),
    )
