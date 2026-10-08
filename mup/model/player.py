from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
from mup.model.item import Item

MAX_LEVEL = 400  # usual 0.97 cap


def level_exp(level):
    """Total exp a character has when it reaches level: the client's next level exp (0x45c980) of level - 1."""
    n = level - 1
    exp = 10 * (n + 9) * n * n
    if n > 255:
        exp += 1000 * (n - 246) * (n - 255) ** 2
    return exp


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

# skill numbers a new character starts with, usual: wizards have energy ball, the others learn or wear theirs
DEFAULT_SKILLS = {
    CharacterClass.DARK_WIZARD: [17],
}


@dataclass
class CombatValues:
    """What class, level, stats and worn items give, see mup.server.stats. Damage per hand, the left hand's is used
    with a bow."""
    damage_min: int = 0
    damage_max: int = 0
    left_min: int = 0
    left_max: int = 0
    magic_min: int = 0
    magic_max: int = 0
    staff_rise: int = 0  # % more wizardry damage
    attack_rate: int = 0
    attack_speed: int = 0
    magic_speed: int = 0
    defense: int = 0
    defense_rate: int = 0
    # options the client doesn't count in its values
    critical_rate: int = 0  # %, luck
    excellent_rate: int = 0  # %
    damage_decrease: int = 0  # % of the damage taken
    reflect: int = 0  # % of the damage taken
    life_bonus: int = 0  # % of the maximum
    mana_bonus: int = 0
    life_after_kill: int = 0  # options: + max / 8 each
    mana_after_kill: int = 0
    zen_bonus: int = 0  # % more zen from monsters
    life_recovery: int = 0  # % of the max life more with each regeneration, option 41


@dataclass
class Player:
    id: int = None  # characters.id, None until stored
    account_id: int = None
    index: int = 0  # character list slot, 0..4
    name: str = 'unset'
    level: int = 1
    exp: int = 0  # total, as the client keeps it
    role_code: int = 0  # ctl code
    class_type: CharacterClass = CharacterClass.DARK_WIZARD
    state: int = 0  # effects bits of the players in view packet, mup.server.effect
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
    chaos_box: Dict[int, Item] = field(default_factory=dict)  # slot (8 x 4) -> item put in the chaos machine
    skills: List[Optional[int]] = field(default_factory=list)  # list slot -> skill number, None: free
    key_settings: Optional[bytes] = None  # F3 30 as the client sent it, [4..17]
    # in game only, times are the game clock (GameServer.now)
    respawn_at: Optional[float] = None  # when a dead character comes back
    next_regen_at: float = 0.0
    next_attack_at: float = 0.0  # attacks and skills are paced, mup.server.combat.paced
    walk_path: List[Tuple[int, int]] = field(default_factory=list)  # tiles of the last walk, start to end
    values: CombatValues = field(default_factory=CombatValues)  # mup.server.stats.update keeps it
    effects: Dict[int, object] = field(default_factory=dict)  # skill number -> mup.server.effect.Effect

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
        life = int(c.life + (self.level - 1) * c.level_life + (self.vitality - c.vitality) * c.vitality_life)
        return min(0xFFFF, life + life * self.values.life_bonus // 100)

    @property
    def max_mana(self):
        c = self.class_info
        mana = int(c.mana + (self.level - 1) * c.level_mana + (self.energy - c.energy) * c.energy_mana)
        return min(0xFFFF, mana + mana * self.values.mana_bonus // 100)

    @property
    def next_exp(self):
        """Total exp of the next level."""
        return level_exp(self.level + 1)

    def skill(self, index):
        """Skill number for a skill list index the client sent."""
        return self.skills[index] if index < len(self.skills) else None
