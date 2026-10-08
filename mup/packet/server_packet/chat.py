from mup.packet.base import Packet, C1, Text, str10, u8


class Chat(Packet):
    """C1 00: [3..12] who speaks, [13..] the line (the client copies 60 bytes). ~ party and @ guild lines keep the
    prefix, the client strips it."""
    code = C1, 0x00
    fields = (
        (3, 'name', str10),
        (13, 'message', Text()),
    )


class Whisper(Packet):
    """C1 02: [3..12] who whispers, [13..] the message (the client copies 60 bytes)."""
    code = C1, 0x02
    fields = (
        (3, 'name', str10),
        (13, 'message', Text()),
    )


class WhisperFailed(Packet):
    """C1 0C: [3] 0 "No users" under the name last whispered to."""
    code = C1, 0x0C
    size = 4
    fields = (
        (3, 'result', u8, 0),
    )
