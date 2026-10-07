from mup.packet.base import Packet, C3, Raw, str10, u32


class LoginRequest(Packet):
    """C3 F1 01: account and password arrive xored with FC CF AB, Crypt.decrypt undoes it."""
    code = C3, 0xF1, 0x01
    size = 49
    fields = (
        (4, 'login', str10),
        (14, 'passw', str10),
        (24, 'tick', u32),  # GetTickCount
        (28, 'version', Raw(5)),
        (33, 'serial', Raw(16)),
    )
