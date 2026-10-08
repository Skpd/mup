from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class MonsterInfo:
    """A monster type, a line of the server's Monster/Monster.txt."""
    number: int  # monster type, picks the model in the client
    name: str
    level: int
    life: int
    damage_min: int
    damage_max: int
    defense: int
    attack_rate: int
    defense_rate: int
    move_range: int  # tiles it wanders from where it stands
    attack_range: int
    view_range: int  # tiles within which it notices players
    move_speed: int  # ms per step
    attack_speed: int  # ms between attacks
    regen_time: int  # seconds until it respawns
    item_rate: int = 0  # drop chances, see mup.server.loot. 0: never
    money_rate: int = 0
    max_item_level: int = 0


@dataclass(frozen=True)
class Spawn:
    """Where monsters of a type appear, a line of the server's Monster/MonsterSetBase.txt."""
    number: int  # monster type
    map_id: int
    xs: range
    ys: range
    leash: int  # how far from its spawn spot a monster chases before it returns
    count: int = 1


@dataclass(eq=False)
class Monster:
    cid: int
    info: MonsterInfo
    spawn: Spawn
    map_id: int = 0
    x: int = 0
    y: int = 0
    direction: int = 0
    life: int = 0
    state: int = 0  # effects bits of the monsters in view packet
    dead: bool = True  # until spawned
    home: Tuple[int, int] = (0, 0)  # where it spawned, it wanders around it and returns to it
    # ai, times are the game clock (GameServer.now)
    target: object = None  # connection it chases
    returning: bool = False
    path: List[Tuple[int, int]] = field(default_factory=list)  # tiles still to walk
    next_step_at: float = 0.0
    next_attack_at: float = 0.0
    next_think_at: float = 0.0
    respawn_at: Optional[float] = None

    @property
    def type_id(self):
        return self.info.number

    @property
    def max_life(self):
        return self.info.life

    @property
    def walk_target(self):
        """Where it is walking to, its own tile when it stands."""
        return self.path[-1] if self.path else (self.x, self.y)
