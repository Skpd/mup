from mup.packet.base import Packet, C3, u8


class MapMove(Packet):
    """C3 1C: puts the player at x, y of a map, must be encrypted."""
    code = C3, 0x1C
    size = 8
    fields = (
        (3, 'map_change', u8, 1),  # 0: teleport on the same map with the teleport animation
        (4, 'map', u8),
        (5, 'x', u8),
        (6, 'y', u8),
        (7, 'direction', u8),
    )
