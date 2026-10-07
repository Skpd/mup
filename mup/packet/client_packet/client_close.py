from mup.packet.base import Packet, C1, u8


class ClientClose(Packet):
    """C1 F1 03: client report. Sent encrypted with a random byte appended when the reason is 6."""
    code = C1, 0xF1, 0x03
    size = 5
    fields = (
        (4, 'reason', u8),
    )

    reasons = {
        0: 'a packet that must be encrypted arrived unencrypted',
        6: 'decrypt failed',
    }
