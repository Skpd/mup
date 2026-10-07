from mup.model.player import Player

# todo items
# rh, lh - item index, 0xFF - empty
# h << 4 | a, p << 4 | g - item index, 0xF + overflow bit - empty
# b << 4 | w << 2 | pet
# item levels, 3 bytes: rh | lh << 3 | h << 3 | a << 3 | p << 3 | g << 3 | b << 3
# item overflow flag, 1 bit each: h a p g b, 0xF8 - none of them is set
# excl flag, 1bit each
EMPTY_EQUIPMENT = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0xF8, 0x00]


def appearance(p: Player):
    """Class and equipment as shown in character list and to other players, 11 bytes."""
    return bytearray([p.class_type.value, *EMPTY_EQUIPMENT])
