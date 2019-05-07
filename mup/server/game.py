from datetime import datetime
from random import randint, choice
from mup.common.interval import Interval
from mup.mapper.account import AccountMapper
from mup.mapper.player import PlayerMapper
from mup.model.monster import Monster
from mup.model.player import Player
from mup.packet.server import SServerJoin, SMeetMonster
from mup.server.base import ServerBase


class GameServer(ServerBase):
    viewport_width = 16
    viewport_bit = 4  # bit length of viewport width - 1

    def __init__(self, loop):
        super().__init__()
        self.loop = loop

        self.player_mapper = PlayerMapper()
        self.account_mapper = AccountMapper()

        # VP init
        self.viewports = {map_id: {} for map_id in range(16)}
        for map_id in range(16):
            for x in range(0, 255, self.viewport_width):
                for y in range(0, 255, self.viewport_width):
                    self.viewports[map_id][(x, y, x + self.viewport_width, y + self.viewport_width)] = {}


        mob = Monster(0x0f, 6)
        mob.x = 127
        mob.y = 189
        mob.dead = False
        self.connections[mob.cid] = mob
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
            print('Added Mob #{}:#{} to {} with xy {}:{}'.format(mob.type_id, mob.cid, vp_key, mob.x, mob.y))

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
                m.life = m.max_life
                m.x = choice(m.spawn_area[0])
                m.y = choice(m.spawn_area[1])
                m.dead = False

                for c in self.get_players_within(m.x, m.y):
                    c.write(SMeetMonster(m))

    def monster_move(self):
        for _, m in self.connections.items():
            if isinstance(m, Monster) and not m.dead:
                if callable(m.move_strategy):
                    # print('calling ', m.move_strategy, m, self)
                    m.move_strategy(m, self)

    def get_players_within(self, x, y, distance=16):
        return self.get_all_within_distance(x, y, distance=distance, class_match=Player)

    def get_monsters_within(self, x, y, distance=16):
        return self.get_all_within_distance(x, y, distance=distance, class_match=Monster)

    def get_all_within_distance(self, x, y, distance=16, class_match=None):
        result = []
        for _, c in self.connections.items():
            if isinstance(c, Monster) and not c.dead:
                if class_match is None or class_match == Monster:
                    if abs(c.x - x) <= distance and abs(c.y - y) <= distance:
                        result.append(c)
            if hasattr(c, 'player') and c.player is not None:
                if class_match is None or class_match == Player:
                    if abs(c.player.x - x) <= distance and abs(c.player.y - y) <= distance:
                        result.append(c)
        return result

    def get_my_viewport(self, map_id, x, y):
        vpx = x >> self.viewport_bit << self.viewport_bit
        vpy = y >> self.viewport_bit << self.viewport_bit
        return self.viewports[map_id][(vpx, vpy, vpx + self.viewport_width, vpy + self.viewport_width)]

    # vp vp vp
    # vp xy vp
    # vp vp vp
    def get_adjacent_viewports(self, map_id, x, y):
        vpx = x >> self.viewport_bit << self.viewport_bit
        vpy = y >> self.viewport_bit << self.viewport_bit
        w = self.viewport_width

        cells = []
        for my in [-1, 0, 1]:
            for mx in [-1, 0, 1]:
                k = (
                    vpx + w*mx, vpy + w*my,
                    vpx + w + w*mx, vpy + w + w*my
                )
                cell = self.viewports[map_id][k] if all([x >= 0 for x in k]) else {}
                cells.append(cell)

        return cells

    def disconnect(self, c):
        p = c.player
        self.player_mapper.store(p)
        del self.get_my_viewport(p.map_id, p.x, p.y)[c.cid]
        del self.connections[c.cid]

    def add_connection(self, c):
        # todo
        c.cid = 4808
        # c.cid = len(self.connections)
        self.connections[c.cid] = c
        print('added connection', c)
        c.write(SServerJoin())

    def get_player_connection(self, c):
        if c in self.connections:
            if c.playing:
                return c

        return None
