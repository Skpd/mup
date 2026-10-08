from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class SkillInfo:
    """A skill: the client's skill.bmd record, with the server values of Skill.txt."""
    number: int  # skill.bmd record index, what server packets carry
    name: str
    level: int  # the drop level of its scroll / orb
    damage: int
    mana: int
    distance: int  # tiles
    # Skill.txt, a later server version
    radius: int = 0  # tiles an area skill reaches around its point
    effect: int = 0
    classes: Tuple[int, int, int, int] = (0, 0, 0, 0)  # dark wizard, dark knight, elf, magic gladiator: 0 no, 1 yes,
    # 2 second class only
