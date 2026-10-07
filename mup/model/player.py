from dataclasses import dataclass, field
from enum import Enum
from typing import List
from mup.model.account import Account
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


# skill numbers, list index is what the client sends when casting
DEFAULT_SKILLS = {
    # energy ball, poison, meteorite, lightning, fire ball, flame, teleport, ice, twister, evil spirit
    CharacterClass.DARK_WIZARD: [17, 1, 2, 3, 4, 5, 6, 7, 8, 9],
}


@dataclass
class Player:
    id: object = None
    player_id: int = 0
    index: int = 0
    name: str = 'unset'
    level: int = 1
    exp: int = 0
    role_code: int = 0
    class_type: CharacterClass = CharacterClass.DARK_WIZARD
    state: int = 0
    life: int = 100
    max_life: int = 200
    mana: int = 1000
    max_mana: int = 2000
    strength: int = 10
    agility: int = 2000
    vitality: int = 10
    energy: int = 10
    free_points: int = 0
    zen: int = 31337
    pk: int = 3
    map_id: int = 0
    x: int = 128
    y: int = 188
    direction: int = 0
    inventory: List[Item] = field(default_factory=list)
    skills: List[int] = field(default_factory=list)
    account: Account = None

    @property
    def next_exp(self):
        if self.level < 255:
            return (9 + self.level) * self.level ** 2 * 10
        else:
            return (9 + (self.level - 255)) * (self.level-255)**2 * 1000

    def skill(self, index):
        """Skill number for a skill list index the client sent."""
        return self.skills[index] if index < len(self.skills) else None
