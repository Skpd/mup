from mup.packet.base import Packet, C1


class CharList(Packet):
    """C1 F3 00: character list request."""
    code = C1, 0xF3, 0x00
    size = 4
