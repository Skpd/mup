from mup.packet.base import Packet, C1, Text, str10


class Chat(Packet):
    """C1 00: [3..12] own name, [13..] the line, at most 60 bytes with its zero. ~ party, @ guild, the client sends
    the line as typed."""
    code = C1, 0x00
    fields = (
        (3, 'name', str10),
        (13, 'message', Text()),
    )


class Whisper(Packet):
    """C1 02: [3..12] the name whispered to, [13..] the message as in 00."""
    code = C1, 0x02
    fields = (
        (3, 'name', str10),
        (13, 'message', Text()),
    )
