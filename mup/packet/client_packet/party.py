from mup.packet.base import Packet, C1, C3, cid, u8


class PartyRequest(Packet):
    """C3 40: ask the player [3..4] to join the party (/party typed next to it)."""
    code = C3, 0x40
    size = 5
    fields = (
        (3, 'cid', cid),
    )


class PartyAnswer(Packet):
    """C3 41: [3] 1 joins the party of [4..5] (the cid of the 40 question), 0 refuses."""
    code = C3, 0x41
    size = 6
    fields = (
        (3, 'answer', u8),
        (4, 'cid', cid),
    )


class PartyLeave(Packet):
    """C1 43: the member at index [3] of the list leaves: the player itself, or anyone when the leader clicks."""
    code = C1, 0x43
    size = 4
    fields = (
        (3, 'member', u8),
    )
