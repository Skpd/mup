from mup.packet.base import Packet, C1


class Handshake(Packet):
    """C1 00 01: connect server hello, the client answers with a server list request."""
    code = C1, 0x00, 0x01
    size = 4
