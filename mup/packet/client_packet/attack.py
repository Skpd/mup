from mup.packet.base import Packet, C1, cid, u8


class Attack(Packet):
    """C1 15: melee attack."""
    code = C1, 0x15
    size = 7
    fields = (
        (3, 'attacked_cid', cid),
        (5, 'action', u8),  # attack animation, sent to others in the action packet
        (6, 'direction', u8),
    )
