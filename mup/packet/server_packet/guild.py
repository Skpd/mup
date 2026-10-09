from mup.packet.base import Packet, Entry, C1, C2, Raw, Str, cid, str10, u8, u16be, u32

class GuildRequest(Packet):
    """C1 50: the player [3..4] asks the guild master to join (dialog 119), the answer is 51 with the cid."""
    code = C1, 0x50
    size = 5
    fields = (
        (3, 'cid', u16be),
    )


class GuildResult(Packet):
    """C1 51: [3] the answer to a guild join request, a line in the chat log (Text 503..510)."""
    code = C1, 0x51
    size = 4
    fields = (
        (3, 'result', u8),
    )

    REFUSED, JOINED, FULL, GONE, NOT_MASTER, IN_GUILD, BUSY, LEVEL = range(8)


class GuildList(Packet):
    """C2 52: the members for the guild window: [4] result, [5] count, [8..11] the guild's score, 12 bytes per member
    from [16]: name, [+10] its number, [+11] 0x80 | server while online (the window shows server + 1), 0 offline.
    The first is the master."""
    code = C2, 0x52
    fields = (
        (4, 'result', u8, 1),
        (8, 'score', u32, 0),
    )
    entry = Entry(count=(5, u8), size=12, start=16, fields=(
        (0, 'name', str10),
        (10, 'number', u8),
        (11, 'server', u8),
    ))

    ONLINE = 0x80

    @classmethod
    def of(cls, members, score=0):
        """members: (name, online) in the list's order"""
        return cls(score=score, entries=[{'name': name, 'number': n, 'server': cls.ONLINE if online else 0}
                                         for n, (name, online) in enumerate(members)])


class GuildLeaveResult(Packet):
    """C1 53: [3] 0 wrong personal code, 1 left, 2 only the master may, 3 put out, 4 the guild is gone (the hero's
    guild cleared). 1 and 4 also close the guild window."""
    code = C1, 0x53
    size = 4
    fields = (
        (3, 'result', u8),
    )

    WRONG_CODE, LEFT, NOT_MASTER, PUT_OUT, DISBANDED = range(5)


class GuildMasterQuestion(Packet):
    """C1 54: the guild master's window: "Do you wish to be the guild master?" (Text 181), answered with 54."""
    code = C1, 0x54
    size = 3


class GuildEditor(Packet):
    """C1 55: the guild master's window goes on to the name and the mark, answered with 55 or 57."""
    code = C1, 0x55
    size = 3


class GuildCreateResult(Packet):
    """C1 56: [3] 1 created (the window closes), 0 the name is taken, 2 the name is too short, 3 already in a
    guild (Text 516..518)."""
    code = C1, 0x56
    size = 4
    fields = (
        (3, 'result', u8),
    )

    TAKEN, CREATED, SHORT, IN_GUILD = range(4)


class GuildInfos(Packet):
    """C2 5A: guilds for the client's list (found by name): number, name, mark (64 colours, 4 bits each)."""
    code = C2, 0x5A
    entry = Entry(count=(4, u8), size=42, fields=(
        (0, 'number', u16be),
        (2, 'name', Str(8)),
        (10, 'mark', Raw(32)),
    ))

    @classmethod
    def of(cls, guilds):
        return cls(entries=[{'number': g.id, 'name': g.name, 'mark': g.mark} for g in guilds])


class GuildMembers(Packet):
    """C2 5B: the guild (by number, known from 5A) of each player [+0..1]: its mark beside the name."""
    code = C2, 0x5B
    entry = Entry(count=(4, u8), size=4, fields=(
        (0, 'cid', cid),
        (2, 'number', u16be),
    ))

    @classmethod
    def of(cls, members):
        """members: (cid, guild number)"""
        return cls(entries=[{'cid': c, 'number': n} for c, n in members])


class GuildMember(Packet):
    """C1 5C: the player [3..4] is in the guild [5..12] with the mark [13..44] (put in the client's list without a
    number)."""
    code = C1, 0x5C
    size = 45
    fields = (
        (3, 'cid', u16be),
        (5, 'name', Str(8)),
        (13, 'mark', Raw(32)),
    )


class GuildGone(Packet):
    """C1 5D: the player [3..4] has no guild anymore. Also closes the guild window."""
    code = C1, 0x5D
    size = 5
    fields = (
        (3, 'cid', u16be),
    )
