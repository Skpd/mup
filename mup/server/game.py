import asyncio
import logging
from collections import Counter, deque
from itertools import count
from mup.config import Config
from mup.model.item import Item
from mup.packet.server import SServerJoin, SStats, SMeetPlayer, SSkillList, SMove, SKeySettings
from mup.repository import database
from mup.repository.account import AccountRepository
from mup.repository.character import CharacterRepository
from mup.server import (ai, chaos, combat, effect, gate, ground, inventory, item, loot, monster, npc, shop, skill,
                        stats, summon, view)
from mup.server.base import ServerBase
from mup.server.character import respawn_gate
from mup.server.world import load_maps

logger = logging.getLogger(__name__)

TERRAIN_PATH = 'data/terrain'  # the client's World*/Terrain*.att
GATE_PATH = 'data/Gate.bmd'  # the client's
ITEM_PATH = 'data/item.bmd'  # the client's
SKILL_PATH = 'data/skill.bmd'  # the client's
TICK = 0.1  # seconds between game ticks


class GameServer(ServerBase):
    """
    The game: connections by cid, maps with the players, monsters and ground items on them. Packets are handled as
    they arrive, everything that happens on its own (monsters, respawns, regeneration, ground items going away,
    autosave) runs in the tick.
    """
    first_player_cid = 4800  # monsters take the lower ids

    def __init__(self, loop, config: Config):
        super().__init__()
        self.loop = loop
        self.config = config
        self.cids = count(self.first_player_cid)

        self.item_info = item.load_info(ITEM_PATH, config.item_info)
        self.fixed_drops = loot.load_fixed(config.item_drops, self.item_info)
        self.skills = skill.load(SKILL_PATH, config.skill_info)
        self.shops = shop.load(config.shops, self.item_info)  # NPC type -> Shop
        self.mixes = chaos.load(config.mixes)
        self.ground = ground.Ground()

        self.db = database.connect(config.db_path)
        self.accounts = AccountRepository(self.db)
        self.characters = CharacterRepository(self.db, self.item_info)
        self.serials = count(self.characters.last_item_serial() + 1)  # of new items

        self.maps = load_maps(TERRAIN_PATH)
        self.gates = gate.load(GATE_PATH)
        self.monster_info = info = monster.load_info(config.monster_info)
        spawns = monster.load_spawns(config.monster_spawns, info)
        self.monsters = {m.cid: m for m in monster.create(spawns, info, count(1), self.first_player_cid - 1)}
        self.dead_monsters = set()
        self.affected = set()  # players (connections) and monsters with effects, mup.server.effect
        now = self.now
        missing = [m for m in self.monsters.values() if not monster.spawn(self, m, now)]
        if missing:
            # spawns of the later version's file on tiles that are walls in this client's terrain
            logger.warning('No free spot for %s monsters, left out: %s', len(missing), dict(Counter(
                '{} {}'.format(self.maps[m.map_id].name, m.info.name) for m in missing)))
            for m in missing:
                del self.monsters[m.cid]
        npcs = sum(m.npc for m in self.monsters.values())
        logger.info('%s monsters and %s NPCs on %s maps', len(self.monsters) - npcs, npcs,
                    len({m.map_id for m in self.monsters.values()}))
        # summons take the monster ids left
        self.summon_cids = deque(range(max(self.monsters, default=0) + 1, self.first_player_cid))
        logger.info('%s item types, fixed drops for %s monster types, %s shops', len(self.item_info),
                    len(self.fixed_drops), len(self.shops))

        self.next_save = now + config.autosave_interval
        self.task = None

    @property
    def now(self):
        """The game clock, seconds."""
        return self.loop.time()

    def start(self):
        self.task = self.loop.create_task(self.run())

    async def run(self):
        next_tick = self.now
        while True:
            self.tick(self.now)
            next_tick += TICK
            delay = next_tick - self.now
            if delay < 0:
                if delay < -1:
                    logger.warning('Game tick %.0f ms late', -delay * 1000)
                next_tick = self.now
                delay = 0
            await asyncio.sleep(delay)

    def tick(self, now):
        """One step of the game: monsters near players act, the dead come back, regeneration, ground items go away,
        autosave."""
        for m in self.maps.values():
            if len(m.players):
                self._run(ai.tick, self, m, now)
        for mob in [mob for mob in self.dead_monsters if mob.respawn_at <= now]:
            if mob.owner is not None:
                self._run(summon.gone, self, mob)  # summons don't come back
            else:
                self._run(monster.respawn, self, mob, now)
        if len(self.ground):
            self._run(ground.tick, self, now)
        if self.affected:
            self._run(effect.tick, self, now)
        for c in self.playing():
            self._run(self._player_tick, c, now)
        if now >= self.next_save:
            self.next_save = now + self.config.autosave_interval
            self._run(self.save_all)

    @staticmethod
    def _run(step, *args):
        # one failing step doesn't stop the others
        try:
            step(*args)
        except Exception:
            logger.exception('%s failed', step.__name__)

    def _player_tick(self, c, now):
        p = c.player
        npc.check(self, c)
        if p.respawn_at is not None:
            if now >= p.respawn_at:
                combat.respawn(self, c)
        elif now >= p.next_regen_at:
            p.next_regen_at = now + combat.REGEN_INTERVAL
            combat.regen(c)

    def new_item(self, info, **values):
        """A new Item of type info with the next serial, full durability unless values has one."""
        new = Item(info, serial=next(self.serials), **values)
        if 'durability' not in values:
            new.durability = item.max_durability(new)
        return new

    def playing(self):
        return [c for c in self.connections.values() if c.player is not None]

    def gate_spot(self, number):
        """Map and a random walkable tile of a gate's area."""
        g = self.gates[number]
        x, y = self.maps[g.map_id].terrain.random_spot(g.xs, g.ys)
        return g.map_id, x, y

    def enter_world(self, c, p):
        """c enters the game with character p: character info, then the player appears on its map."""
        m = self.maps.get(p.map_id)
        if p.dead or m is None or not m.terrain.walkable(p.x, p.y):
            # died and left, or stands where nobody can
            p.map_id, p.x, p.y = self.gate_spot(respawn_gate(p.map_id if m is not None else 0))
            p.life = p.max_life
        p.respawn_at = None
        p.next_regen_at = self.now + combat.REGEN_INTERVAL
        p.walk_path = []
        c.player = p
        c.playing = True
        c.view = set()

        p.values = stats.compute(p)
        p.life, p.mana = min(p.life, p.max_life), min(p.mana, p.max_mana)
        chaos.return_items(self, c, notify=False)  # left in the chaos machine without room, the inventory goes below
        skill.update_weapon_skills(self, c, notify=False)  # the list goes out below
        # no weather packet (0x0F): this client ignores what other versions send on join
        c.write(SStats.of(p))
        inventory.send(c)
        c.write(SMeetPlayer.of([(c.cid, p)]))
        c.write(SSkillList.of(p.skills))
        if p.key_settings:
            c.write(SKeySettings.of(p.key_settings))  # after the list, the client finds the hotkeys' skills in it
        self.maps[p.map_id].add_player(c)
        view.refresh(self, c)

    def leave_world(self, c):
        """Saves the character of connection c and takes it out of the game, the account stays logged in."""
        npc.close(self, c, leaving=True)
        effect.clear(self, c)
        summon.dismiss(self, c)
        self.save(c)
        view.forget(self, c)
        self.maps[c.player.map_id].remove_player(c)
        c.player = None
        c.playing = False

    def walk(self, c, x, y, direction):
        """c's player walks to x, y on its map: the players who see it get the walk."""
        p = c.player
        self.maps[p.map_id].move_player(c, x, y)
        p.direction = direction
        move = SMove(cid=c.cid, x=x, y=y, direction=direction << 4)
        for o in view.refresh(self, c):
            o.write(move)

    def relocate(self, c, map_id, x, y, direction, announce):
        """
        c's player moves to x, y of map_id at once. announce(player) is the packet telling the client (1C, F3 04),
        the client clears its objects on it, so everything in view is sent again.
        """
        p = c.player
        npc.close(self, c, notify=True)  # F3 04 closes the client's NPC windows, 1C its vault
        if map_id != p.map_id:
            summon.dismiss(self, c)
        view.forget(self, c)
        self.maps[p.map_id].remove_player(c)
        p.map_id, p.x, p.y, p.direction = map_id, x, y, direction
        p.walk_path = []
        self.maps[map_id].add_player(c)
        c.write(announce(p))
        view.refresh(self, c)

    def disconnect(self, c):
        self.connections.pop(c.cid, None)
        if c.player is not None:
            self.leave_world(c)

    def account_online(self, account_id):
        return any(c.acc is not None and c.acc.id == account_id for c in self.connections.values())

    def save(self, c):
        """Writes the character of connection c, with the account's vault when it was opened. A failed write is
        logged, the game goes on."""
        try:
            self.characters.save(c.player, c.warehouse)
        except Exception:
            logger.exception('Failed to save %s', c.player.name)

    def save_all(self):
        players = self.playing()
        for c in players:
            self.save(c)
        if players:
            logger.info('Saved %s characters', len(players))

    def shutdown(self):
        """Saves the characters in game and closes the database."""
        if self.task is not None:
            self.task.cancel()
        self.save_all()
        self.db.close()

    def add_connection(self, c):
        c.cid = next(self.cids)
        self.connections[c.cid] = c
        c.write(SServerJoin(cid=c.cid))
