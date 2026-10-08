from mup.packet.base import Packet, Entry, C1, u8


class SkillList(Packet):
    """C1 F3 11: skills, at most 20. The list index is what the client sends when casting."""
    code = C1, 0xF3, 0x11
    entry = Entry(count=(4, u8), size=3, fields=(
        (0, 'slot', u8),
        (1, 'skill', u8),
    ))

    @classmethod
    def of(cls, skills):
        """skills: list index -> skill number, None for a free slot."""
        return cls(entries=[{'slot': i, 'skill': s} for i, s in enumerate(skills) if s is not None])


class SkillChange(Packet):
    """C1 F3 11 with FE in the count: one skill set in a slot of the list, FF: the slot emptied."""
    code = C1, 0xF3, 0x11
    size = 7
    fields = (
        (4, 'change', u8),
        (5, 'slot', u8),
        (6, 'skill', u8, 0),
    )

    ADD = 0xFE
    REMOVE = 0xFF
