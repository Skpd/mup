from mup.packet.base import Packet, C4, u8


class Inventory(Packet):
    """C4 F3 10: must be encrypted. Sent empty until the item layout is known (roadmap M3)."""
    code = C4, 0xF3, 0x10
    size = 6
    fields = (
        (5, 'item_count', u8, 0),  # then slot + item data per item
    )
