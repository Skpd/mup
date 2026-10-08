from mup.model.item import (GROUP_SIZE, DINORANT, RIGHT_HAND, LEFT_HAND, HELM, ARMOR, PANTS, GLOVES, BOOTS, WINGS,
                            PET, glow)
from mup.model.player import Player

ARMOR_SLOTS = (HELM, ARMOR, PANTS, GLOVES, BOOTS)  # groups 7..11, 5 bit index each, 31 is empty
LEVEL_SLOTS = (RIGHT_HAND, LEFT_HAND) + ARMOR_SLOTS  # 3 bit glow each in [5..7], right hand in the low bits
NONE = 3  # wings and pet bits when empty


def equipment(p: Player):
    """
    Equipment as shown in character list and to other players, 10 bytes (client 0x43f6f0):
    [0] right hand type, [1] left hand type (FF empty), [2..4] helm, armor, pants, gloves, boots index nibbles,
    [4] wings << 2 | pet, [5..7] glow levels, [8] the index bits 4 and Dinorant, [9] excellent bits.
    """
    inv = p.inventory
    look = bytearray(10)
    look[0] = inv[RIGHT_HAND].type if RIGHT_HAND in inv else 0xFF
    look[1] = inv[LEFT_HAND].type if LEFT_HAND in inv else 0xFF

    for n, slot in enumerate(ARMOR_SLOTS):
        item = inv.get(slot)
        index = item.type - (7 + n) * GROUP_SIZE if item is not None else 31
        nibble = (index & 0x0F) << (4 if n % 2 == 0 else 0)
        look[2 + n // 2] |= nibble
        look[8] |= (index >> 4 & 1) << (7 - n)
        if item is not None and item.excellent:
            look[9] |= 0x80 >> n

    wings = inv.get(WINGS)
    look[4] |= (wings.info.index if wings is not None and wings.info.index < NONE else NONE) << 2
    pet = inv.get(PET)
    if pet is not None and pet.type == DINORANT:
        look[4] |= NONE
        look[8] |= 0x04
    else:
        look[4] |= pet.info.index if pet is not None and pet.info.index < NONE else NONE

    levels = 0
    for n, slot in enumerate(LEVEL_SLOTS):
        if slot in inv:
            levels |= glow(inv[slot].level) << 3 * n
    look[5:8] = levels.to_bytes(3, 'big')
    for n, slot in enumerate((RIGHT_HAND, LEFT_HAND)):
        if slot in inv and inv[slot].excellent:
            look[9] |= 0x04 >> n
    return bytes(look)
