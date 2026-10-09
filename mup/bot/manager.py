"""
The bots of a game: logged in when the game server starts (bots_enabled) or by a simulation, driven by the game tick
(each bot thinks every 0.5..1 s, staggered), logged out with the game. Their characters are saved like players', each
bot's row with it. What the bots decide goes to trace (a callable of one dict per event) when it is set.
"""
import logging
from mup.bot import career
from mup.bot.flow import Flows
from mup.bot.session import BotSession
from mup.packet.client import CJoinGame
from mup.repository.bot import BotRepository

logger = logging.getLogger(__name__)


class BotManager:
    def __init__(self, game):
        self.game = game
        self.store = BotRepository(game.db)
        self.flows = Flows(game)
        self.sessions = {}  # character id -> BotSession, in login order
        self.tap = None  # LocalSession.tap of the sessions, a simulation's digest
        self.trace = None  # callable(dict) for the events of the bots
        self._grounds = None
        self._sellers = None
        game.bots = self

    @property
    def grounds(self):
        """Map -> cell -> mup.bot.career.Ground, laid out when first needed."""
        if self._grounds is None:
            self._grounds = career.load_grounds(self.game)
        return self._grounds

    @property
    def sellers(self):
        """Item type -> [(NPC type, map, x, y)] of the shops that sell it: the shops' goods and the NPCs' spots of the
        game's data, laid out when first needed."""
        if self._sellers is None:
            found = {}
            for npc in sorted(self.game.monsters.values(), key=lambda m: m.cid):
                goods = self.game.shops.get(npc.type_id) if npc.npc else None
                for t in sorted({i.type for i in goods.items.values()}) if goods is not None else ():
                    found.setdefault(t, []).append((npc.type_id, npc.map_id, npc.spawn.xs.start, npc.spawn.ys.start))
            self._sellers = found
        return self._sellers

    def login_all(self):
        bots = self.store.all()
        for bot in bots:
            self.login(bot)
        logger.info('%s bots in game', len(self.sessions))

    def login(self, bot, brain=True):
        """bot's session connects and enters the game with its character, as a client does. Its BotSession, None
        when it couldn't enter."""
        game = self.game
        c = BotSession(self, bot, brain)
        c.connected = True
        game.add_connection(c)  # the cid and SServerJoin
        c.joined = True
        c.acc = game.accounts.load_id(bot.account_id)
        c.send(CJoinGame(name=bot.name))
        if c.player is None:
            logger.warning('Bot %s did not enter the game', bot.name)
            c.disconnect()
            return None
        self.sessions[bot.character_id] = c
        if c.brain is not None:
            c.brain.start(game.now)
        logger.info('Bot %s enters the game, level %s at %s %s,%s', bot.name, c.player.level, c.player.map_id,
                    c.player.x, c.player.y)
        return c

    def logout(self, c):
        """c leaves the game as when a client's connection drops, its character and row saved."""
        self.sessions.pop(c.bot.character_id, None)
        c.disconnect()

    def tick(self, now):
        for c in list(self.sessions.values()):
            if c.connected and c.player is not None:
                c.tick(now)

    def event(self, c, kind, values):
        if self.trace is None:
            return
        p = c.player
        a = c.brain.activity if c.brain is not None else None
        record = {'t': round(self.game.now, 1), 'bot': c.bot.name, 'activity': a.name if a else None, 'event': kind}
        if p is not None:
            record.update(map=p.map_id, x=p.x, y=p.y, life=p.life)
        target = c.motor.target
        if target is not None:
            record['target'] = target.cid
        record.update(values)
        self.trace(record)
