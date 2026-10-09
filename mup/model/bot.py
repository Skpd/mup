from dataclasses import dataclass, field, asdict, fields


@dataclass
class Personality:
    """What sets one bot apart from another of its class, drawn from its seed when it is made (mup.bot.account)."""
    risk: float = 0.5  # 0 careful .. 1 reckless: how much of its life a kill may cost
    rest_below: float = 0.4  # share of its life it rests below
    rest_until: float = 0.9  # and rests up to

    @classmethod
    def roll(cls, rng):
        return cls(risk=round(rng.uniform(0.2, 0.8), 2), rest_below=round(rng.uniform(0.3, 0.5), 2),
                   rest_until=round(rng.uniform(0.8, 1.0), 2))

    @classmethod
    def of(cls, values):
        """From stored values, the ones it doesn't know left out, the missing ones default."""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in values.items() if k in known})

    def as_dict(self):
        return asdict(self)


@dataclass
class Bot:
    """A row of bots with its character's name and account: a character the server plays (mup.bot)."""
    character_id: int
    name: str
    account_id: int
    seed: int  # of its own random draws
    personality: Personality = field(default_factory=Personality)
    career: dict = field(default_factory=dict)  # what the brain keeps across logins, mup.bot.brain
    schedule: str = ''  # when it plays, empty: whenever the server runs (B0)
