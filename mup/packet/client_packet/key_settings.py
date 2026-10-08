from mup.packet.base import Packet, C1, Raw


class KeySettings(Packet):
    """C1 F3 30: the client's hotkeys, sent on every logout. [4..13] the skill number on hotkey 0..9 (0: none), then
    other settings (not reviewed)."""
    code = C1, 0xF3, 0x30
    size = 18
    fields = (
        (4, 'data', Raw(14)),
    )
