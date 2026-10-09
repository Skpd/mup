from mup.packet.base import Packet, Entry, C1, str10, u8, u32


class DevilSquareResult(Packet):
    """C1 90: the answer to entering. The client closes its windows and sends 31 first, then [3] 0 nothing (the
    server moves the player), 1 no invitation, 2 too late, 3 too strong for the square, 4 too weak, 5 full
    (Text 677, 678, 686, 687, 679)."""
    code = C1, 0x90
    size = 4
    fields = (
        (3, 'result', u8),
    )

    ENTERED, NO_INVITATION, CLOSED, TOO_STRONG, TOO_WEAK, FULL = range(6)


class DevilSquareTime(Packet):
    """C1 91: [3] 0 "You can enter Devil Square now!!", else "Devil Square will open in [3] minutes."
    (Text 643, 644)."""
    code = C1, 0x91
    size = 4
    fields = (
        (3, 'minutes', u8),
    )


class DevilSquareCountdown(Packet):
    """C1 92: a line counting down 30 s: [3] 0 "You will enter Devil Square (%d seconds from now)", 1 "The gate of
    Devil Square will close down in %d seconds", 2 "The gate of Devil Square is closing down (%d seconds remaining)"
    (Text 640..642)."""
    code = C1, 0x92
    size = 4
    fields = (
        (3, 'kind', u8),
    )

    STARTS, ENTRY_CLOSES, ENDS = range(3)


class DevilSquareRanking(Packet):
    """C1 93: the ranking window: [3] the player's rank, [4] count, 24 bytes each from [5]: name, [+12] points,
    [+16] exp, [+20] zen. Entry 0 is the player's own ("My Info", shown last), then the ranks from 1."""
    code = C1, 0x93
    fields = (
        (3, 'rank', u8),
    )
    entry = Entry(count=(4, u8), size=24, fields=(
        (0, 'name', str10),
        (12, 'points', u32),
        (16, 'exp', u32),
        (20, 'zen', u32),
    ))
