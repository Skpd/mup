"""
The game in process on a clock of its own: no sockets and no waiting, game time passes as fast as the ticks run.
Puppets are clients in process, driven by test code (tests/sim.py) or by a policy (Hunter); bots (mup.bot) play
through the game's bot manager. The same seed gives the same game, packet for packet (docs/bots.md, S0).

    with Sim(seed=1, monster_info='tests/...') as sim:
        a = sim.enter('Knight', at=(0, 180, 127))
        a.send(CAttack(...))
        kill = a.recv_until(of(SKill, cid=mob), limit=5)

A scenario (Sim.dump, Sim.load) is a player's situation in a file: the character as stored, the account's vault, a
bot's row and the monsters around it. Loaded, it plays on in a new game of the same seed and data.
"""
import hashlib
import json
import logging
import random
from itertools import count
from mup.bot import account as bot_account
from mup.bot.manager import BotManager
from mup.bot.session import BotSession
from mup.config import Config
from mup.model.monster import Monster
from mup.model.player import CharacterClass
from mup.packet.client import CAttack, CJoinGame, CMove
from mup.packet.server import SKill
from mup.server import character, command, handlers, monster
from mup.server.game import GameServer, TICK
from mup.server.path import direction, find_path
from mup.server.session import LocalSession
from mup.server.world import VIEW_RANGE, distance

logger = logging.getLogger(__name__)

EPOCH = 1_798_761_600.0  # the wall clock at game time 0: 2027-01-01 00:00 UTC
DEFAULTS = dict(db_path=':memory:', log_packets=False)  # Config values of a simulation, the caller's go over them
SCENARIO = 1  # version of the scenario files


class ManualClock:
    """Game time that moves only when the simulation ticks, a wall clock that follows it from EPOCH."""

    def __init__(self, start=0.0):
        self.time = start

    def now(self):
        return self.time

    def wall(self):
        return EPOCH + self.time


class Errors(logging.Handler):
    """The errors the game logs: a failing handler or tick step is logged and the game goes on, a simulation stops on
    it (Sim.check)."""

    def __init__(self):
        super().__init__(logging.ERROR)
        self.records = []

    def emit(self, record):
        self.records.append(record)


class Sim:
    """
    A game server in process. config: Config fields over DEFAULTS, e.g. the test monster files. Log records get a
    game_time attribute while it is open. Close it, or use it as a context manager.
    """

    def __init__(self, seed=0, start=0.0, **config):
        self.seed = seed
        self.start = start
        self.overrides = config
        self.ticks = 0
        self.clock = ManualClock(start)
        self.puppets = []
        self.hash = hashlib.sha256()  # of everything written to the puppets, Sim.digest
        self.errors = Errors()
        logging.getLogger().addHandler(self.errors)
        self._record_factory = logging.getLogRecordFactory()
        logging.setLogRecordFactory(self._record)

        random.seed(seed)  # every draw of the game goes through random
        try:
            self.game = GameServer(None, Config(**{**DEFAULTS, **config}), self.clock)
        except Exception:
            self._unhook()
            raise
        handlers.register(self.game)
        self.bots = BotManager(self.game)
        self.bots.tap = self.tap
        self.check()

    def _record(self, *args, **kwargs):
        record = self._record_factory(*args, **kwargs)
        record.game_time = self.clock.time
        return record

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self._unhook()
        self.game.db.close()

    def _unhook(self):
        logging.setLogRecordFactory(self._record_factory)
        logging.getLogger().removeHandler(self.errors)

    @property
    def now(self):
        return self.clock.time

    def check(self):
        """Raises AssertionError with the errors the game logged since the last check."""
        if self.errors.records:
            records, self.errors.records = self.errors.records, []
            raise AssertionError('the game logged errors:\n' + '\n'.join(
                '{:.1f} {}'.format(r.game_time, self.errors.format(r)) for r in records))

    def step(self):
        """One tick: the puppets act, then the game ticks."""
        self.ticks += 1
        self.clock.time = now = self.start + self.ticks * TICK  # counted, so no float drift over hours
        for c in self.puppets:
            if c.connected:
                c.act(now)
        self.game.tick(now)
        self.check()

    def run(self, seconds):
        """Runs the game for seconds of game time."""
        end = self.ticks + round(seconds / TICK)
        while self.ticks < end:
            self.step()

    def run_until(self, pred, limit=10.0, what='the condition'):
        """Runs the game until pred() holds, at most limit game seconds. Returns the game seconds it took."""
        begin = self.now
        end = self.ticks + round(limit / TICK)
        while not pred():
            if self.ticks >= end:
                raise AssertionError('{} not within {} game seconds'.format(what, limit))
            self.step()
        return self.now - begin

    def enter(self, name, class_type=CharacterClass.DARK_KNIGHT, at=None, level=1, cls=None):
        """
        A new character on an account of its own without password, in game through CJoinGame as a client enters.
        at: (map, x, y), the class's start gate when not given. cls: the Puppet subclass. Returns the puppet.
        """
        game = self.game
        account = game.accounts.create(name, None)
        map_id, x, y = at if at is not None else game.gate_spot(character.start_gate(class_type))
        game.characters.create(character.new_character(account.id, 0, name, class_type, map_id, x, y))
        c = self.connect(account, cls)
        c.send(CJoinGame(name=name))
        if c.player is None:
            raise AssertionError('{} did not enter the game'.format(name))
        if level > 1:
            command.level(game, c, level)
        return c

    def bot(self, name, class_type=CharacterClass.DARK_KNIGHT, at=None, level=1, seed=None, personality=None,
            brain=True):
        """
        A new bot (mup.bot) logged in through the game's manager, at (map, x, y) or the class's start gate. seed: of
        its own draws, from the simulation's seed and its name when not given. brain: False for one only the motor
        moves. Returns its BotSession.
        """
        game = self.game
        at = at if at is not None else game.gate_spot(character.start_gate(class_type))
        if seed is None:
            seed = int.from_bytes(hashlib.sha256('{} {}'.format(self.seed, name).encode()).digest()[:4], 'big')
        c = self.bots.login(bot_account.create(game.db, name, class_type, at, seed, personality), brain)
        if c is None:
            raise AssertionError('bot {} did not enter the game'.format(name))
        if level > 1:
            command.level(game, c, level)
        return c

    def connect(self, account, cls=None):
        """A puppet connected and logged in to account, at character select."""
        c = (cls or Puppet)(self)
        c.connected = True
        self.game.add_connection(c)  # it gets the cid and SServerJoin
        c.joined = True
        c.acc = account
        self.puppets.append(c)
        return c

    def tap(self, c, packet):
        """Everything written to the puppets and the bots goes into the digest, in order."""
        data = bytes(packet)
        self.hash.update(c.cid.to_bytes(2, 'big') + len(data).to_bytes(2, 'big') + data)

    def digest(self):
        """Hex sha256 of every packet written to the puppets, in order: the same seed gives the same digest."""
        return self.hash.hexdigest()

    def dump(self, c, path=None):
        """
        The situation of c's player as a scenario: the character as stored (saved first), its items and skills, the
        account's vault, a bot's row, the living monsters within view range. Written to path as JSON when given,
        returned.
        """
        game, p = self.game, c.player
        game.save(c)
        db = game.db
        character_id, account_id = p.id, c.acc.id
        vault = db.execute('SELECT zen FROM warehouses WHERE account_id = ?', (account_id,)).fetchone()
        m = game.maps[p.map_id]
        scenario = {
            'version': SCENARIO, 'seed': self.seed, 'time': self.now, 'config': self.overrides,
            'puppet': type(c).__name__,
            'character': _row(db.execute('SELECT * FROM characters WHERE id = ?', (character_id,)).fetchone(),
                              'id', 'account_id'),
            'skills': [_row(r, 'character_id') for r in db.execute(
                'SELECT * FROM skills WHERE character_id = ? ORDER BY slot', (character_id,))],
            'items': [_row(r, 'id', 'character_id', 'account_id') for r in db.execute(
                'SELECT * FROM items WHERE character_id = ? ORDER BY serial', (character_id,))],
            'vault': {'zen': vault['zen'] if vault else None, 'items': [
                _row(r, 'id', 'character_id', 'account_id') for r in db.execute(
                    "SELECT * FROM items WHERE account_id = ? AND owner = 'warehouse' ORDER BY serial",
                    (account_id,))]},
            'bot': _row(db.execute('SELECT * FROM bots WHERE character_id = ?', (character_id,)).fetchone(),
                        'character_id') if isinstance(c, BotSession) else None,
            'monsters': [{'cid': mob.cid, 'type': mob.type_id, 'x': mob.x, 'y': mob.y, 'home': list(mob.home),
                          'life': mob.life} for mob in sorted(m.monsters.near(p.x, p.y, VIEW_RANGE),
                                                               key=lambda mob: mob.cid) if mob.attackable],
        }
        if path is not None:
            with open(path, 'w') as f:
                json.dump(scenario, f, indent=1)
        return scenario

    @classmethod
    def load(cls, scenario, puppet=None, **config):
        """
        A new game playing a scenario (a dump or the path of its file) on: its seed, game time and config (config
        goes over it), its monsters placed as they were and the others in view range dead, the character in game: a
        bot through the manager, otherwise a puppet of class puppet. Returns the Sim and the puppet or BotSession.
        """
        if not isinstance(scenario, dict):
            with open(scenario) as f:
                scenario = json.load(f)
        if scenario.get('version') != SCENARIO:
            raise ValueError('scenario version {}, this is {}'.format(scenario.get('version'), SCENARIO))
        sim = cls(scenario['seed'], scenario['time'], **{**scenario['config'], **config})
        game, db = sim.game, sim.game.db
        row = _values(scenario['character'])
        account = game.accounts.create(row['name'], None)
        with db:
            character_id = _insert(db, 'characters', {**row, 'account_id': account.id})
            for r in scenario['skills']:
                _insert(db, 'skills', {**_values(r), 'character_id': character_id})
            for r in scenario['items']:
                _insert(db, 'items', {**_values(r), 'character_id': character_id})
            for r in scenario['vault']['items']:
                _insert(db, 'items', {**_values(r), 'account_id': account.id})
            if scenario['vault']['zen'] is not None:
                _insert(db, 'warehouses', {'account_id': account.id, 'zen': scenario['vault']['zen']})
            if scenario.get('bot') is not None:
                _insert(db, 'bots', {**_values(scenario['bot']), 'character_id': character_id})
        game.serials = count(game.characters.last_item_serial() + 1)  # past the loaded items

        now, map_id, x, y = sim.now, row['map'], row['x'], row['y']
        placed = {d['cid']: d for d in scenario['monsters']}
        for mob in sorted(game.maps[map_id].monsters.near(x, y, VIEW_RANGE), key=lambda mob: mob.cid):
            if mob.attackable and mob.cid not in placed:
                monster.kill(game, mob, now)
        for d in scenario['monsters']:
            mob = game.monsters.get(d['cid'])
            if mob is None or mob.type_id != d['type'] or mob.map_id != map_id:
                logger.warning('Scenario monster %s (type %s) is not in this game, left out', d['cid'], d['type'])
                continue
            monster.place(game, mob, d['x'], d['y'], d['life'], tuple(d['home']), now)

        if scenario.get('bot') is not None:
            c = sim.bots.login(sim.bots.store.load(row['name']))
        else:
            c = sim.connect(account, puppet)
            c.send(CJoinGame(name=row['name']))
        if c is None or c.player is None:
            raise AssertionError('{} did not enter the game'.format(row['name']))
        return sim, c


def _row(row, *leave_out):
    """A database row as JSON values, bytes as {'hex': ...}."""
    return {k: {'hex': row[k].hex()} if isinstance(row[k], bytes) else row[k] for k in row.keys()
            if k not in leave_out}


def _values(row):
    return {k: bytes.fromhex(v['hex']) if isinstance(v, dict) else v for k, v in row.items()}


def _insert(db, table, values):
    cur = db.execute('INSERT INTO {} ({}) VALUES ({})'.format(table, ', '.join(values), ', '.join('?' * len(values))),
                     list(values.values()))
    return cur.lastrowid


def of(cls, **values):
    """Predicate for recv_until: a packet of class cls (SKill, ...) with these attribute values."""
    def pred(p):
        return isinstance(p, cls) and all(getattr(p, k, None) == v for k, v in values.items())
    return pred


class Puppet(LocalSession):
    """
    A client in process driven by test code or a policy: what the game writes lands in inbox, recv_until runs the game
    until a packet comes. act(now) runs every tick before the game's, policies override it.
    """

    def __init__(self, sim):
        super().__init__(sim.game)
        self.sim = sim
        self.tap = sim.tap

    def __repr__(self):
        return '<{} {} {}>'.format(type(self).__name__, self.cid, self.player.name if self.player else '-')

    def send(self, packet):
        super().send(packet)
        self.sim.check()

    def act(self, now):
        pass

    def recv_until(self, pred, limit=5.0, what='the packet'):
        """The first packet in the inbox matching pred, running the game up to limit game seconds for it. It is taken
        out of the inbox, the packets before it stay."""
        end = self.sim.ticks + round(limit / TICK)
        start = 0  # the inbox before it was looked at already
        while True:
            for i in range(start, len(self.inbox)):
                if pred(self.inbox[i]):
                    return self.inbox.pop(i)
            start = len(self.inbox)
            if self.sim.ticks >= end:
                raise AssertionError('{}: no {} within {} game seconds; last packets {}'.format(
                    self, what, limit, [type(p).__name__ for p in self.inbox[-8:]]))
            self.sim.step()


class Hunter(Puppet):
    """
    Hunts the nearest monster in view: walks next to it and swings at it until it dies. With none in view it roams,
    up to RANGE tiles from where it entered: monsters respawn anywhere in their spawn area. A cheap policy for tests,
    the bots (mup.bot) play for real: no looting, no resting, no points; dead, it waits for the respawn and walks back
    out of town.
    """
    THINK = 0.4  # seconds between looks around and between swings, within the server's attack pace
    STEP = 0.4  # seconds per tile walked, slower than the client's (mup.bot.motor.STEP_TIME)
    WALK = 4  # tiles per walk packet
    SWING = 0x64  # the attack animation the client sends
    GIVE_UP = 30.0  # seconds a monster it found no path to is left alone
    ROAM = 24  # tiles to the spots it roams to
    RANGE = 64  # tiles from home it roams within

    def __init__(self, sim):
        super().__init__(sim)
        self.home = None  # map, x, y
        self.rng = None  # its own, so it doesn't take the game's draws
        self.next_at = 0.0
        self.unreachable = {}  # monster cid -> until when it is left alone
        self.route = []  # tiles still to walk to a roaming goal
        self.kills = self.deaths = 0

    def act(self, now):
        for packet in self.inbox:  # it reads only the view, and counts
            if isinstance(packet, SKill):
                self.kills += packet.killer == self.cid
                self.deaths += packet.cid == self.cid
        self.inbox.clear()
        p = self.player
        if p is None or p.dead or now < self.next_at:
            return
        if self.home is None:
            self.home = p.map_id, p.x, p.y
            self.rng = random.Random('{} {}'.format(self.sim.seed, p.name))
        self.next_at = now + self.THINK
        targets = [o for o in self.view if isinstance(o, Monster) and not o.dead and o.attackable
                   and self.unreachable.get(o.cid, 0.0) <= now]
        if not targets:
            self.roam(now)
            return
        self.route = []
        mob = min(targets, key=lambda o: (distance(p.x, p.y, o.x, o.y), o.cid))
        if distance(p.x, p.y, mob.x, mob.y) <= 1:
            self.send(CAttack(attacked_cid=mob.cid, action=self.SWING,
                              direction=direction(mob.x - p.x, mob.y - p.y) or 0))
            return
        path = find_path(self.walkable, (p.x, p.y), (mob.x, mob.y), reach=1, max_steps=16, budget=200)
        if not path:
            self.unreachable[mob.cid] = now + self.GIVE_UP
            return
        self.walk(path, now)

    def walkable(self, x, y):
        return self.server.maps[self.player.map_id].terrain.walkable(x, y)

    def roam(self, now):
        """Walks on towards a random spot, a new one when it got there or was moved; out of town, home first."""
        p = self.player
        map_id, hx, hy = self.home
        if map_id != p.map_id:
            return
        if not self.route or distance(p.x, p.y, *self.route[0]) != 1:
            terrain = self.server.maps[map_id].terrain
            if terrain.safe(p.x, p.y):
                goal = hx, hy
            else:
                goal = (self.rng.randint(p.x - self.ROAM, p.x + self.ROAM),
                        self.rng.randint(p.y - self.ROAM, p.y + self.ROAM))
                if distance(*goal, hx, hy) > self.RANGE or not terrain.walkable(*goal) or terrain.safe(*goal):
                    return
            self.route = find_path(self.walkable, (p.x, p.y), goal, max_steps=128, budget=8000) or []
            if not self.route:
                return
        self.walk(self.route, now)
        del self.route[:self.WALK]

    def walk(self, path, now):
        p = self.player
        steps = []
        x, y = p.x, p.y
        for nx, ny in path[:self.WALK]:
            steps.append(direction(nx - x, ny - y))
            x, y = nx, ny
        self.send(CMove.of(p.x, p.y, steps))
        self.next_at = now + max(self.THINK, len(steps) * self.STEP)
