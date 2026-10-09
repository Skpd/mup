from mup.packet.base import Packet, C3, u8


class QuestStates(Packet):
    """C3 A0: the quest states, asked right before a 30 while the client has no quest class yet."""
    code = C3, 0xA0
    size = 3


class QuestProceed(Packet):
    """C3 A2: proceed with quest [3] ([4] 1): a dialog answer that accepts the quest or hands in its item."""
    code = C3, 0xA2
    size = 5
    fields = (
        (3, 'quest', u8),
        (4, 'value', u8),
    )
