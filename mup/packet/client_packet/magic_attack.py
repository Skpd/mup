from mup.packet.base import Packet, C3, cid, u8


class MagicAttack(Packet):
    """C3 19: skill on a target."""
    code = C3, 0x19
    size = 6
    fields = (
        (3, 'skill_index', u8),  # position in the skill list sent on join, not the skill number
        (4, 'target_cid', cid),
    )
