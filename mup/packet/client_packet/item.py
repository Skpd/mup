from mup.packet.base import Packet, C3, Raw, u8, u16be


class PickUp(Packet):
    """C3 22: pick up an item from the ground."""
    code = C3, 0x22
    size = 5
    fields = (
        (3, 'id', u16be),
    )


class DropItem(Packet):
    """C3 23: drop the item held from slot [5] on x, y."""
    code = C3, 0x23
    size = 6
    fields = (
        (3, 'x', u8),
        (4, 'y', u8),
        (5, 'slot', u8),
    )


class MoveItem(Packet):
    """C3 24: move an item. Windows: 0 inventory (equipment and grid), 1 trade, 2 warehouse, 3 chaos machine."""
    code = C3, 0x24
    size = 11
    fields = (
        (3, 'source_window', u8),
        (4, 'source', u8),
        (5, 'item', Raw(4)),  # the item as the client has it
        (9, 'target_window', u8),
        (10, 'target', u8),
    )


class UseItem(Packet):
    """C3 26: use (right click) the item in an inventory slot: potions, scrolls, jewels on the target slot."""
    code = C3, 0x26
    size = 5
    fields = (
        (3, 'slot', u8),
        (4, 'target', u8),
    )
