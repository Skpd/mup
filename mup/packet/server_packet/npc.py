from mup.packet.base import Packet, Entry, C1, C2, C3, Raw, u8, u32

NONE = bytes(4)


class Talk(Packet):
    """C3 30: must be encrypted. Opens the window of the NPC talked to, [3]: 2 warehouse, 3 chaos machine (with
    [4..7] the Devil Square invitation rates the client shows for levels 2..5), 4 Devil Square, 5 another window,
    anything else the shop."""
    code = C3, 0x30
    size = 8
    fields = (
        (3, 'window', u8),
        (4, 'rates', Raw(4), NONE),
    )

    SHOP, WAREHOUSE, CHAOS_MACHINE = 0, 2, 3


class ItemList(Packet):
    """C2 31: [4] 3 the chaos machine's 8 x 4 box (the client shows that the mix failed), anything else the 8 x 15
    grid the shop and the warehouse share. 5 bytes per item: the slot, the item."""
    code = C2, 0x31
    fields = (
        (4, 'kind', u8),
    )
    entry = Entry(count=(5, u8), size=5, fields=(
        (0, 'slot', u8),
        (1, 'item', Raw(4)),
    ))

    SHOP, CHAOS_BOX = 0, 3

    @classmethod
    def of(cls, kind, items):
        """items: slot -> Item"""
        return cls(kind=kind, entries=[{'slot': slot, 'item': item.encode()} for slot, item in sorted(items.items())])


class BuyResult(Packet):
    """C1 32: [3] the inventory slot of the item bought, [4..7] the item. FF refused. Ends the wait after 32, the
    money comes with 22 FE."""
    code = C1, 0x32
    size = 8
    fields = (
        (3, 'slot', u8),
        (4, 'item', Raw(4)),
    )

    FAILED = 0xFF

    @classmethod
    def failed(cls):
        return cls(slot=cls.FAILED, item=NONE)


class SellResult(Packet):
    """C1 33: [3] 0 refused (the held item goes back), otherwise sold: [4..7] the money."""
    code = C1, 0x33
    size = 8
    fields = (
        (3, 'result', u8),
        (4, 'money', u32, 0),
    )


class RepairResult(Packet):
    """C1 34: [4..7] the money after the repair, 0 changes nothing. The durability comes with 2A first."""
    code = C1, 0x34
    size = 8
    fields = (
        (4, 'money', u32),
    )


class WarehouseMoney(Packet):
    """C1 81: [3] not 0: [4..7] the zen in the vault, [8..11] the money."""
    code = C1, 0x81
    size = 12
    fields = (
        (3, 'result', u8, 1),
        (4, 'stored', u32),
        (8, 'money', u32),
    )


class WarehouseClosed(Packet):
    """C1 82: closes the NPC windows and the inventory, the item held is gone from the cursor."""
    code = C1, 0x82
    size = 3


class MixResult(Packet):
    """C1 86: [3] 1 success: the box holds only [4..7] in slot 0. 2 not enough zen. 0 failed, the box comes with
    31. Other values end the mix without a message."""
    code = C1, 0x86
    size = 8
    fields = (
        (3, 'result', u8),
        (4, 'item', Raw(4), NONE),
    )

    FAILED, SUCCESS, NO_ZEN, REFUSED = 0, 1, 2, 3


class ChaosClosed(Packet):
    """C1 87: closes the NPC windows like 82."""
    code = C1, 0x87
    size = 3
