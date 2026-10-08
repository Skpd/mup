from mup.packet.base import Packet, Entry, C3, cid, u8


class AreaHits(Packet):
    """C3 1D: what an area skill's effect reached as it landed, up to 5 targets, several per cast."""
    code = C3, 0x1D
    fields = (
        (3, 'skill_index', u8),  # position in the skill list, not the skill number
        (4, 'x', u8),  # where the effect landed
        (5, 'y', u8),
        (6, 'serial', u8),
    )
    entry = Entry(count=(7, u8), size=2, fields=(
        (0, 'cid', cid),
    ))
