from mup.packet.base import Packet, C1, C3, cid, u8, u32


class Talk(Packet):
    """C3 30: talk to the NPC [3..4]. The client sends it for types 234 and up, next to the NPC."""
    code = C3, 0x30
    size = 5
    fields = (
        (3, 'cid', cid),
    )


class CloseWindow(Packet):
    """C3 31: the NPC window was closed (also sent going back to character select and by the quest window)."""
    code = C3, 0x31
    size = 3


class Buy(Packet):
    """C3 32: buy the item in slot [3] of the shop's grid."""
    code = C3, 0x32
    size = 4
    fields = (
        (3, 'slot', u8),
    )


class Sell(Packet):
    """C3 33: sell the item held, from inventory slot [3] (dropped on the shop window)."""
    code = C3, 0x33
    size = 4
    fields = (
        (3, 'slot', u8),
    )


class Repair(Packet):
    """C3 34: repair the item in inventory slot [3], FF all. [4] 1 from the inventory window (5% dearer), 0 at the
    smith's shop."""
    code = C3, 0x34
    size = 5
    fields = (
        (3, 'slot', u8),
        (4, 'own', u8),
    )

    ALL = 0xFF


class WarehouseMoney(Packet):
    """C1 81: [3] 0 deposit, 1 withdraw [4..7] zen."""
    code = C1, 0x81
    size = 8
    fields = (
        (3, 'type', u8),
        (4, 'amount', u32),
    )

    DEPOSIT, WITHDRAW = 0, 1


class WarehouseClose(Packet):
    """C1 82: the vault was closed, the client closed its windows itself."""
    code = C1, 0x82
    size = 3


class Mix(Packet):
    """C1 86: mix what is in the chaos machine, after the client recognised a mix and the player agreed."""
    code = C1, 0x86
    size = 3


class ChaosClose(Packet):
    """C1 87: the chaos machine was closed, the client allows that only with an empty box."""
    code = C1, 0x87
    size = 3
