from mup.packet.base import Packet, C1, C3, Raw, cid, u8

NONE = bytes(4)


class PickUpResult(Packet):
    """C1 22: [3] inventory slot and the item, FE and the money total (big endian), FF nothing picked up."""
    code = C1, 0x22
    size = 8
    fields = (
        (3, 'slot', u8),
        (4, 'data', Raw(4)),
    )

    ZEN = 0xFE
    FAILED = 0xFF

    @classmethod
    def item(cls, slot, item):
        return cls(slot=slot, data=item.encode())

    @classmethod
    def zen(cls, total):
        return cls(slot=cls.ZEN, data=total.to_bytes(4, 'big'))

    @classmethod
    def failed(cls):
        return cls(slot=cls.FAILED, data=NONE)


class DropResult(Packet):
    """C1 23: [3] 0 refused (the held item goes back), 1 dropped from slot [4]."""
    code = C1, 0x23
    size = 5
    fields = (
        (3, 'result', u8),
        (4, 'slot', u8),
    )


class MoveItemResult(Packet):
    """C3 24: must be encrypted. [3] window (0 inventory) and [4] slot the item went to, FF refused."""
    code = C3, 0x24
    size = 9
    fields = (
        (3, 'window', u8),
        (4, 'slot', u8),
        (5, 'item', Raw(4)),
    )

    INVENTORY = 0
    FAILED = 0xFF

    @classmethod
    def failed(cls):
        return cls(window=cls.FAILED, slot=0, item=NONE)


class LookChange(Packet):
    """C1 25: one equipment slot of a player changed. The item bytes with [6] = slot << 4 | level, [5] FF empty."""
    code = C1, 0x25
    size = 9
    fields = (
        (3, 'cid', cid),
        (5, 'type', u8),
        (6, 'slot_level', u8),
        (7, 'durability', u8, 0),
        (8, 'extra', u8),  # item byte 3: excellent bits, type bit 8
    )

    @classmethod
    def of(cls, c, slot, item, level):
        """level: what the client expects for the slot, the item level for the right hand, else the glow index."""
        if item is None:
            return cls(cid=c, type=0xFF, slot_level=slot << 4, extra=0)
        data = item.encode()
        return cls(cid=c, type=data[0], slot_level=slot << 4 | level & 0x0F, extra=data[3])


class ItemDeleted(Packet):
    """C1 28: the item in slot [3] is gone (FF: none), [4] not 0 unlocks item use."""
    code = C1, 0x28
    size = 5
    fields = (
        (3, 'slot', u8),
        (4, 'unlock', u8, 1),
    )


class Durability(Packet):
    """C1 2A: durability (the count of potions) of the item in slot [3], [5] not 0 unlocks item use."""
    code = C1, 0x2A
    size = 6
    fields = (
        (3, 'slot', u8),
        (4, 'durability', u8),
        (5, 'unlock', u8, 1),
    )
