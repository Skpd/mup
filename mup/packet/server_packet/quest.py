from mup.packet.base import Packet, Entry, C1, cid, u8


class QuestStates(Packet):
    """C1 A0: the quest state bytes, 2 bits per quest (see mup.server.quest.position). The client zeroes its 50 and
    copies [3] of them, and takes the quest class from the hero's class: the only place it does."""
    code = C1, 0xA0
    entry = Entry(count=(3, u8), size=1, fields=(
        (0, 'value', u8),
    ))

    @classmethod
    def of(cls, states):
        return cls(entries=[{'value': b} for b in states])


class QuestDialog(Packet):
    """C1 A1: opens the quest window for quest [3], [4] stored as its state byte (quest >> 2), the text by the
    quest's state."""
    code = C1, 0xA1
    size = 5
    fields = (
        (3, 'quest', u8),
        (4, 'states', u8),
    )


class QuestResult(Packet):
    """C1 A2: [4] 0: as A1 for quest [3] with the state byte [5]. Other results are ignored by the client."""
    code = C1, 0xA2
    size = 6
    fields = (
        (3, 'quest', u8),
        (4, 'result', u8, 0),
        (5, 'states', u8),
    )


class QuestReward(Packet):
    """C1 A3: a reward for the player [3..4]: [5] C8 level up points [6] (added when it is the hero), C9 the class
    [6] (class << 5 | 2nd class << 4). Both show an effect with a sound."""
    code = C1, 0xA3
    size = 7
    fields = (
        (3, 'cid', cid),
        (5, 'type', u8),
        (6, 'value', u8),
    )

    POINTS, CLASS = 0xC8, 0xC9
