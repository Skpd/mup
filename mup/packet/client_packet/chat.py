from mup.packet.base import Packet, C1, Text, str10


class Chat(Packet):
    """C1 00: layout not reviewed in the client yet."""
    code = C1, 0x00
    fields = (
        (3, 'name', str10),
        (13, 'message', Text()),
    )
