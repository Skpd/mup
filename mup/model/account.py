from dataclasses import dataclass


@dataclass
class Account:
    id: object = None
    name: str = ''
    password: str = ''
    active: bool = True
