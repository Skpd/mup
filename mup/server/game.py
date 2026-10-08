import logging
from datetime import datetime
from itertools import count
from random import randint, choice
from mup.common.interval import Interval
from mup.config import Config
from mup.model.monster import Monster
from mup.model.player import Player
from mup.packet.server import SServerJoin, SMeetMonster, SClear
from mup.repository import database
from mup.repository.account import AccountRepository
from mup.repository.character import CharacterRepository
from mup.server.base import ServerBase

logger = logging.getLogger(__name__)

# placeholders until the monster spawns of roadmap M2: weak monsters just outside each Lorencia town exit, the client
# doesn't allow attacks in the safe zone. Monster type, x and y range of an open area (Terrain1.att)
LORENCIA_EXITS = [
    (2, range(130, 139), range(82, 87)),  # north, budge dragons
    (3, range(177, 186), range(124, 129)),  # east, spiders
    (3, range(129, 139), range(173, 178)),  # south, spiders
    (2, range(87, 94), range(124, 132)),  # west, budge dragons
]
MONSTERS_PER_EXIT = 3


class GameServer(ServerBase):
    viewport_width = 16
    viewport_bit = 4  # bit length of viewport width - 1
    first_player_cid = 4800  # monsters take the lower ids

    def __init__(self, loop, config: Config):
        super().__init__()
        self.loop = loop
        self.config = config
        self.cids = count(self.first_player_cid)

        self.db = database.connect(config.db_path)
        self.accounts = AccountRepository(self.db)
        self.characters = CharacterRepository(self.db)

        cids = count(1)
        for type_id, xs, ys in LORENCIA_EXITS:
            for _ in range(MONSTERS_PER_EXIT):
                mob = Monster(next(cids), type_id)
                mob.spawn_area = (xs, ys)
                mob.x = choice(xs)
                mob.y = choice(ys)
                mob.dead = False
                self.connections[mob.cid] = mob

        # respawn init
        self.monster_spawner = Interval(self.monster_spawn, 1)
        self.monster_spawner.start()

        self.autosave = Interval(self.save_all, config.autosave_interval)
        self.autosave.start()
        return

        # spawn
        vp_start_x = 128 >> self.viewport_bit << self.viewport_bit
        vp_start_y = 188 >> self.viewport_bit << self.viewport_bit
        vp_key = (vp_start_x, vp_start_y, vp_start_x+self.viewport_width, vp_start_y+self.viewport_width)
        for i in range(1, 10):
            mob = Monster(i, 6)
            mob.spawn_area = (
                range(vp_start_x, vp_start_x + self.viewport_width),
                range(vp_start_y, vp_start_y + self.viewport_width)
            )
            mob.dead = True
            # mob.x = random.randint(vp_start_x, vp_start_x + self.viewport_width)
            # mob.y = random.randint(vp_start_y, vp_start_y + self.viewport_width)
            # if i % 2 == 0:
            # from mup.server.move_strategy.passive_scared import move
            # else:
            from mup.server.move_strategy.passive_wander import move

            mob.move_strategy = move
            # mob.move_strategy = None

            self.connections[mob.cid] = mob
            # self.viewports[0][vp_key][mob.cid] = mob
            logger.debug('Added Mob #%s:#%s to %s with xy %s:%s', mob.type_id, mob.cid, vp_key, mob.x, mob.y)

        # mover init
        self.monster_mover = Interval(self.monster_move, 1)
        self.monster_mover.start()

        # respawn init
        self.monster_spawner = Interval(self.monster_spawn, 1)
        self.monster_spawner.start()

    def monster_spawn(self):
        now = int(datetime.utcnow().timestamp())
        for _, m in self.connections.items():
            if isinstance(m, Monster) and m.dead and (m.died_at + m.respawn_interval) <= now:
                # players near the corpse may still have it
                for c in self.get_players_within(m.map_id, m.x, m.y):
                    c.write(SClear.of([m.cid]))

                m.life = m.max_life
                m.x = choice(m.spawn_area[0])
                m.y = choice(m.spawn_area[1])
                m.dead = False

                for c in self.get_players_within(m.map_id, m.x, m.y):
                    c.write(SMeetMonster.of([m]))

    def monster_move(self):
        for _, m in self.connections.items():
            if isinstance(m, Monster) and not m.dead:
                if callable(m.move_strategy):
                    # print('calling ', m.move_strategy, m, self)
                    m.move_strategy(m, self)

    def get_players_within(self, map_id, x, y, distance=16):
        return self.get_all_within_distance(map_id, x, y, distance=distance, class_match=Player)

    def get_monsters_within(self, map_id, x, y, distance=16):
        return self.get_all_within_distance(map_id, x, y, distance=distance, class_match=Monster)

    def get_all_within_distance(self, map_id, x, y, distance=16, class_match=None):
        result = []
        for _, c in self.connections.items():
            if isinstance(c, Monster) and not c.dead and c.map_id == map_id:
                if class_match is None or class_match == Monster:
                    if abs(c.x - x) <= distance and abs(c.y - y) <= distance:
                        result.append(c)
            if getattr(c, 'player', None) is not None and c.player.map_id == map_id:
                if class_match is None or class_match == Player:
                    if abs(c.player.x - x) <= distance and abs(c.player.y - y) <= distance:
                        result.append(c)
        return result

    def disconnect(self, c):
        self.connections.pop(c.cid, None)
        if c.player is not None:
            self.leave_world(c)

    def leave_world(self, c):
        """Saves the character of connection c and takes it out of the game, the account stays logged in."""
        p = c.player
        self.save(c)
        c.player = None
        c.playing = False
        for other in self.get_players_within(p.map_id, p.x, p.y):
            other.write(SClear.of([c.cid]))

    def account_online(self, account_id):
        return any(getattr(c, 'acc', None) is not None and c.acc.id == account_id for c in self.connections.values())

    def save(self, c):
        """Writes the character of connection c. A failed write is logged, the game goes on."""
        try:
            self.characters.save(c.player)
        except Exception:
            logger.exception('Failed to save %s', c.player.name)

    def save_all(self):
        players = [c for c in self.connections.values() if getattr(c, 'player', None) is not None]
        for c in players:
            self.save(c)
        if players:
            logger.info('Saved %s characters', len(players))

    def shutdown(self):
        """Saves the characters in game and closes the database."""
        self.monster_spawner.stop()
        self.autosave.stop()
        self.save_all()
        self.db.close()

    def add_connection(self, c):
        c.cid = next(self.cids)
        self.connections[c.cid] = c
        c.write(SServerJoin(cid=c.cid))

    def get_player_connection(self, c):
        if c in self.connections:
            if c.playing:
                return c

        return None
