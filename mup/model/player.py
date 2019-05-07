from typing import List
from mup.model.account import Account
from mup.model.item import Item

BASE_EXP = 100
EXP_LOG = 5


class Player:
    id: object
    player_id: int = 0
    index: int = 0
    name: str = 0
    level: int = 1
    exp: int = 0
    role_code: int = 0
    class_type: int = 0
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
    inventory: List[Item] = []
    account: Account = Account()

    @property
    def next_exp(self):
        if self.level < 255:
            return (9 + self.level) * self.level ** 2 * 10
        else:
            return (9 + (self.level - 255)) * (self.level-255)**2 * 1000
