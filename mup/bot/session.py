import random
from collections import Counter
from mup.bot.brain import Brain
from mup.bot.checker import Checker
from mup.bot.motor import Motor
from mup.server.session import LocalSession


class BotSession(LocalSession):
    """
    A bot's connection: in process, the game can't tell it from a client's. What it sends goes through the handlers
    as bytes and through the fair play checker, what the game writes is its perception (the brain reads the inbox
    every tick). brain: False for a bot only the motor moves (tests).
    """

    def __init__(self, manager, bot, brain=True):
        super().__init__(manager.game)
        self.manager = manager
        self.bot = bot
        self.rng = random.Random(bot.seed)  # its own, so its choices don't take the game's draws
        self.tap = manager.tap
        self.counts = Counter()  # kills, deaths, levels, stuck, errors, refused, 'time <activity>'
        self.sent = Counter()  # packet class name -> sent
        self.motor = Motor(self)
        self.checker = Checker(self)
        self.brain = Brain(self) if brain else None
        self.acting_at = None  # game time of the tick it acts in: the motor's time, the server's clock moves on

    def __repr__(self):
        return '<BotSession {} {}>'.format(self.cid, self.bot.name)

    @property
    def walkable(self):
        """can_step(x, y) on its map, the tiles it walks on (mup.bot.flow) without the cells it keeps out of."""
        return self.manager.flows.walkable(self.player.map_id, self.brain.blocked if self.brain else frozenset())

    def tick(self, now):
        """Every game tick: the packets it got (the answers to its requests first), the brain when it is time to
        think, the motor."""
        self.acting_at = now
        packets, self.inbox = self.inbox, []
        self.checker.received(packets)
        self.motor.perceive(packets, now)
        if self.brain is not None:
            self.brain.perceive(packets, now)
            self.brain.tick(now)
        self.motor.tick(now)

    def send(self, packet):
        now = self.acting_at if self.acting_at is not None else self.server.now
        self.sent[type(packet).__name__] += 1
        state = self.checker.before(packet, now)
        super().send(packet)
        self.checker.after(packet, state, now)

    def saved(self):
        if self.brain is not None:
            self.bot.career = self.brain.career_state()
        self.manager.store.save(self.bot)

    def event(self, kind, **values):
        self.manager.event(self, kind, values)
