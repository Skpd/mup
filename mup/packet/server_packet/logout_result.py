from mup.packet.base import Packet, C3, u8


class LogoutResult(Packet):
    """C3 F1 02: answer to the logout request, the client acts on the type. 1 and 2 must be encrypted."""
    code = C3, 0xF1, 0x02
    size = 5
    fields = (
        (4, 'type', u8),
    )

    CLOSE = 0  # the client closes its window
    CHARACTER_SELECT = 1  # back to character select, the client requests the character list
    SERVER_SELECT = 2  # the client closes the connection and goes back to the server list
