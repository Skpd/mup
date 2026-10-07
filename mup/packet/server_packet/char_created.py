from mup.packet.base import Packet, C1, str10, u8


class CharCreated(Packet):
    """C1 F3 01: result 1 ok, 0 and 2 show different errors. Class and look come from the create screen."""
    code = C1, 0xF3, 0x01
    size = 16
    fields = (
        (4, 'result', u8),
        (5, 'name', str10, ''),
        (15, 'slot', u8, 0),
    )
