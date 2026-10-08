from dataclasses import dataclass, field
from typing import Dict
from mup.model.item import Item


@dataclass
class Warehouse:
    """An account's vault: zen and items in an 8 x 15 grid, slot -> item like the inventory grid from 0."""
    account_id: int
    zen: int = 0
    items: Dict[int, Item] = field(default_factory=dict)
