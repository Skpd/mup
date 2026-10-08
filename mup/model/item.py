from dataclasses import dataclass
from typing import Optional, Tuple

GROUP_SIZE = 32  # item type = group * 32 + index
ZEN = 14 * GROUP_SIZE + 15  # the type the client shows zen on the ground with
BOLT = 4 * GROUP_SIZE + 7
ARROWS = 4 * GROUP_SIZE + 15
DINORANT = 13 * GROUP_SIZE + 3

# inventory slots: equipment, then the 8 x 8 grid
RIGHT_HAND, LEFT_HAND, HELM, ARMOR, PANTS, GLOVES, BOOTS, WINGS, PET, PENDANT, RING, RING2 = range(12)
GRID = 12
GRID_SIZE = 8

GLOW = (0, 3, 5, 7, 8, 9, 10, 11)  # glow index -> item level the client draws it with (client 0x43f680)


def glow(level):
    """The 3 bit glow index of the equipment look for an item level."""
    return max(i for i, at in enumerate(GLOW) if level >= at)


@dataclass(frozen=True)
class ItemInfo:
    """An item type: the client's item.bmd record, with the server values of Item.txt."""
    type: int
    name: str
    two_handed: bool
    level: int  # drop level
    width: int
    height: int
    damage_min: int
    damage_max: int
    defense_rate: int
    defense: int
    magic_defense: int
    attack_speed: int
    walk_speed: int
    durability: int
    magic_durability: int
    strength: int  # requirement bases, see mup.server.item.requirements
    agility: int
    energy: int
    level_required: int
    value: int
    classes: Tuple[int, int, int, int]  # dark wizard, dark knight, elf, magic gladiator: 0 no, 1 yes, 2 second class
    resistances: Tuple[int, int, int, int]  # ice, poison, lightning, fire
    # Item.txt, a later server version
    skill: bool = False  # can come with its skill
    options: bool = False  # can come with luck and an option
    drops: bool = False  # monsters drop it

    @property
    def group(self):
        return self.type // GROUP_SIZE

    @property
    def index(self):
        return self.type % GROUP_SIZE


@dataclass(eq=False)
class Item:
    """An item someone has or that lies on the ground. The serial is unique among all items."""
    info: ItemInfo
    level: int = 0  # 0..15
    durability: int = 0  # the count for potions
    skill: bool = False
    luck: bool = False
    option: int = 0  # 0..7
    excellent: int = 0  # 6 bits
    serial: Optional[int] = None
    wear: int = 0  # use since the last durability point it lost, mup.server.item.wear, not stored

    @property
    def type(self):
        return self.info.type

    def encode(self):
        """The 4 item bytes of the packets, see Items in docs/protocol-097.md."""
        return bytes([
            self.type & 0xFF,
            self.skill << 7 | (self.level & 0x0F) << 3 | self.luck << 2 | self.option & 0x03,
            min(self.durability, 0xFF),
            (self.type >> 8) << 7 | (self.option >> 2 & 1) << 6 | self.excellent & 0x3F,
        ])

    def __repr__(self):
        return '<Item {} +{} #{}>'.format(self.info.name, self.level, self.serial)


@dataclass(eq=False)
class GroundItem:
    """An item or zen lying on a map. Ids are the client's ground item slots, 0..999."""
    id: int
    map_id: int
    x: int
    y: int
    item: Optional[Item] = None  # None: zen
    zen: int = 0
    owner: object = None  # connection that may pick it up alone until owner_until
    owner_until: float = 0.0
    expires_at: float = 0.0
