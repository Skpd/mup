from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
from mup.model.item import Item

BASE_EXP = 100
EXP_LOG = 5


class CharacterClass(Enum):
    """
    0.97 class byte: class << 5 | second evo << 4
    """
    DARK_WIZARD = 0
    SOUL_MASTER = 16
    DARK_KNIGHT = 32
    BLADE_KNIGHT = 48
    ELF = 64
    MUSE_ELF = 80
    MAGIC_GLADIATOR = 96

    @property
    def base(self):
        """The first class: soul master -> dark wizard."""
        return CharacterClass(self.value & 0xE0)


@dataclass(frozen=True)
class ClassInfo:
    """Base stats and how life / mana grow, server Data/Character/DefaultClassInfo.txt."""
    strength: int
    agility: int
    vitality: int
    energy: int
    life: int
    mana: int
    level_life: float
    level_mana: float
    vitality_life: float
    energy_mana: float
    level_points: int  # level up points per level


CLASS_INFO = {
    CharacterClass.DARK_WIZARD: ClassInfo(18, 18, 15, 30, 60, 60, 1.0, 2.0, 2.0, 2.0, 5),
    CharacterClass.DARK_KNIGHT: ClassInfo(28, 20, 25, 10, 110, 20, 2.0, 0.5, 3.0, 1.0, 5),
    CharacterClass.ELF: ClassInfo(22, 25, 20, 15, 80, 30, 1.0, 1.5, 2.0, 1.5, 5),
    CharacterClass.MAGIC_GLADIATOR: ClassInfo(26, 26, 26, 26, 110, 60, 1.0, 1.0, 2.0, 2.0, 7),
}

# skill numbers, list index is what the client sends when casting
DEFAULT_SKILLS = {
    # energy ball, poison, meteorite, lightning, fire ball, flame, teleport, ice, twister, evil spirit
    CharacterClass.DARK_WIZARD: [17, 1, 2, 3, 4, 5, 6, 7, 8, 9],
}


@dataclass
class Player:
    id: int = None  # characters.id, None until stored
    account_id: int = None
    index: int = 0  # character list slot, 0..4
    name: str = 'unset'
    level: int = 1
    exp: int = 0
    role_code: int = 0  # ctl code
    class_type: CharacterClass = CharacterClass.DARK_WIZARD
    state: int = 0
    life: int = 60
    mana: int = 60
    strength: int = 18
    agility: int = 18
    vitality: int = 15
    energy: int = 30
    free_points: int = 0
    zen: int = 0
    pk: int = 3  # pk level, 3 is a commoner
    pk_count: int = 0
    quest_state: bytes = b''
    map_id: int = 0
    x: int = 128
    y: int = 188
    direction: int = 0
    inventory: Dict[int, Item] = field(default_factory=dict)  # slot -> item, see mup.model.item
    skills: List[int] = field(default_factory=list)
    # in game only, times are the game clock (GameServer.now)
    respawn_at: Optional[float] = None  # when a dead character comes back
    next_regen_at: float = 0.0
    walk_path: List[Tuple[int, int]] = field(default_factory=list)  # tiles of the last walk, start to end

    @classmethod
    def new(cls, class_type: CharacterClass, **values):
        """A level 1 character with the class base stats, full life and mana."""
        info = CLASS_INFO[class_type.base]
        p = cls(class_type=class_type, strength=info.strength, agility=info.agility, vitality=info.vitality,
                energy=info.energy, **values)
        p.life = p.max_life
        p.mana = p.max_mana
        return p

    @property
    def dead(self):
        return self.life <= 0

    @property
    def class_info(self):
        return CLASS_INFO[self.class_type.base]

    @property
    def max_life(self):
        c = self.class_info
        return int(c.life + (self.level - 1) * c.level_life + (self.vitality - c.vitality) * c.vitality_life)

    @property
    def max_mana(self):
        c = self.class_info
        return int(c.mana + (self.level - 1) * c.level_mana + (self.energy - c.energy) * c.energy_mana)

    @property
    def next_exp(self):
        if self.level < 255:
            return (9 + self.level) * self.level ** 2 * 10
        else:
            return (9 + (self.level - 255)) * (self.level-255)**2 * 1000

    def skill(self, index):
        """Skill number for a skill list index the client sent."""
        return self.skills[index] if index < len(self.skills) else None
