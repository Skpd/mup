from mup.packet.base import Packet, C1, u8


class Rotate(Packet):
    """C1 18: animation, turning sends 0x66."""
    code = C1, 0x18
    size = 5
    fields = (
        (3, 'direction', u8),
        (4, 'action', u8),
    )
