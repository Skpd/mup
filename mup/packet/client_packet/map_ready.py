from mup.packet.base import Packet, C1


class MapReady(Packet):
    """C1 F3 12: sent after a map change (1C) is done."""
    code = C1, 0xF3, 0x12
    size = 4
