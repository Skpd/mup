"""
The elf's summons (skills 30..36, from the summon orb): a monster of her own that follows her and attacks what she
attacks (mup.server.ai.summon_update). One at a time, gone when it dies, she dies, leaves the map or the game, or
summons another. Players see it with 1F (13 with the owner's name, client 0x4172c0). Monsters don't go for summons
and players can't hit them (mup's choice for now).
"""
import logging
from mup.model.monster import Monster, Spawn
from mup.server import monster, view

logger = logging.getLogger(__name__)

# skill -> monster type, the usual 0.97 summons: goblin, stone golem, assassin, elite yeti, dark knight, bali, soldier
TYPES = {30: 26, 31: 32, 32: 21, 33: 20, 34: 10, 35: 150, 36: 151}
NOT_ON = {10}  # maps without summons: Icarus, the client doesn't send the skill there
GUARD = 8  # tiles from its owner it goes for a target


def call(game, c, number):
    """c's player summons with skill number next to it, the one it had goes. False when it can't."""
    p = c.player
    info = game.monster_info.get(TYPES.get(number))
    if info is None or p.map_id in NOT_ON or not game.summon_cids:
        return False
    m = game.maps[p.map_id]
    spot = m.terrain.random_spot(range(p.x - 1, p.x + 2), range(p.y - 1, p.y + 2), m.monster_can_stand)
    if spot is None:
        return False
    dismiss(game, c)
    here = Spawn(info.number, p.map_id, range(spot[0], spot[0] + 1), range(spot[1], spot[1] + 1), GUARD)
    mob = Monster(game.summon_cids.popleft(), info, here, map_id=p.map_id, owner=c)
    game.monsters[mob.cid] = mob
    monster.spawn(game, mob, game.now)
    c.summon = mob
    logger.info('%s summons %s %s', p.name, info.name, mob.cid)
    return True


def dismiss(game, c):
    """c's summon goes away."""
    mob = c.summon
    if mob is None:
        return
    c.summon = None
    if not mob.dead:
        game.maps[mob.map_id].remove_monster(mob)
    gone(game, mob)


def gone(game, mob):
    """A summon leaves the game (or its corpse goes), its cid is free again."""
    if mob.owner is not None and mob.owner.summon is mob:
        mob.owner.summon = None
    view.monster_removed(game, mob)
    game.monsters.pop(mob.cid, None)
    game.dead_monsters.discard(mob)
    game.affected.discard(mob)
    game.summon_cids.append(mob.cid)


def owner_attacks(c, target):
    """c's player attacks target, a monster: its summon goes for it too."""
    mob = c.summon
    if mob is not None and target is not mob and target.owner is None:
        mob.target = target
