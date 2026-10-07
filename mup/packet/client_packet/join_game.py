from mup.packet.base import Packet, C1, str10


class JoinGame(Packet):
    """C1 F3 03: enter the game with a character."""
    code = C1, 0xF3, 0x03
    size = 14
    fields = (
        (4, 'name', str10),
    )
