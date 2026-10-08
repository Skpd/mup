from mup.packet.base import Packet, C3, u8


class Logout(Packet):
    """C3 F1 02: leave the game. Usual layout, the client's sender isn't found yet (docs/protocol-097.md)."""
    code = C3, 0xF1, 0x02
    size = 5
    fields = (
        (4, 'type', u8),  # SLogoutResult.CLOSE, CHARACTER_SELECT, SERVER_SELECT
    )
