from mup.packet.base import Packet, C1, C3, cid, u8, u32


class TradeRequest(Packet):
    """C3 36: ask the player [3..4] to trade (/trade typed next to it)."""
    code = C3, 0x36
    size = 5
    fields = (
        (3, 'cid', cid),
    )


class TradeAnswer(Packet):
    """C1 37: [3] 1 trades with who asked, 0 refuses."""
    code = C1, 0x37
    size = 4
    fields = (
        (3, 'answer', u8),
    )


class TradeZen(Packet):
    """C1 3A: [4..7] the zen put into the trade, replacing what was in it."""
    code = C1, 0x3A
    size = 8
    fields = (
        (4, 'amount', u32),
    )


class TradeOk(Packet):
    """C3 3C: [3] 1 ok, 0 not ok any more."""
    code = C3, 0x3C
    size = 4
    fields = (
        (3, 'ok', u8),
    )


class TradeCancel(Packet):
    """C3 3D: the trade window's cancel button or its close."""
    code = C3, 0x3D
    size = 3
