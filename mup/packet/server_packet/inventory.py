from mup.packet.base import Packet, Entry, C4, Raw, u8


class Inventory(Packet):
    """C4 F3 10: equipment and grid, must be encrypted. Slots 0..11 equipment, 12..75 the 8 x 8 grid."""
    code = C4, 0xF3, 0x10
    entry = Entry(count=(5, u8), size=5, fields=(
        (0, 'slot', u8),
        (1, 'item', Raw(4)),
    ))

    @classmethod
    def of(cls, inventory):
        """inventory: slot -> Item"""
        return cls(entries=[{'slot': slot, 'item': item.encode()} for slot, item in sorted(inventory.items())])
