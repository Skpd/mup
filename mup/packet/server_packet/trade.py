from mup.packet.base import Packet, C1, C3, Raw, str10, u8, u16, u32


class TradeRequest(Packet):
    """C3 36: must be encrypted. [3..12] the name of who asks to trade, the client asks its player (answer 37)."""
    code = C3, 0x36
    size = 13
    fields = (
        (3, 'name', str10),
    )


class TradeAnswer(Packet):
    """C1 37: [3] 1 the trade window opens with the partner's name, level and guild number, 0 refused (Your trade
    has been canceled), 2 not possible now."""
    code = C1, 0x37
    size = 20
    fields = (
        (3, 'result', u8),
        (4, 'name', str10, ''),
        (14, 'level', u16, 0),
        (16, 'guild', u32, 0),
    )

    REFUSED, OPEN, BUSY = 0, 1, 2


class TradeItemGone(Packet):
    """C1 38: the item in slot [3] of the partner's grid is gone."""
    code = C1, 0x38
    size = 4
    fields = (
        (3, 'slot', u8),
    )


class TradeItem(Packet):
    """C1 39: the partner put the item [4..7] in slot [3] of its grid."""
    code = C1, 0x39
    size = 8
    fields = (
        (3, 'slot', u8),
        (4, 'item', Raw(4)),
    )


class TradeZen(Packet):
    """C1 3A: [3] 1 the zen the client asked for is in the trade, 0 none is."""
    code = C1, 0x3A
    size = 4
    fields = (
        (3, 'result', u8),
    )


class PartnerZen(Packet):
    """C1 3B: [4..7] the zen the partner put in."""
    code = C1, 0x3B
    size = 8
    fields = (
        (4, 'amount', u32),
    )


class TradeOk(Packet):
    """C1 3C: [3] 0 the partner's ok is off, 1 on, 2 the own ok is off."""
    code = C1, 0x3C
    size = 4
    fields = (
        (3, 'state', u8),
    )

    PARTNER_OFF, PARTNER_ON, OWN_OFF = 0, 1, 2


class TradeEnd(Packet):
    """C1 3D: closes the trade and the inventory, [3] the message: 0 canceled, 1 done (none), 2 no room, 3 the
    request was canceled. The client keeps none of the trade's items, F3 10 and 22 FE follow."""
    code = C1, 0x3D
    size = 4
    fields = (
        (3, 'result', u8),
    )

    CANCELED, DONE, NO_ROOM, REQUEST_CANCELED = 0, 1, 2, 3
