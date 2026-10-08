"""Monster types and spawns from the server's Monster.txt / MonsterSetBase.txt, and putting monsters on the maps."""
import logging
import shlex
from collections import Counter
from mup.model.monster import Monster, MonsterInfo, Spawn
from mup.server import view
from mup.server.world import MAP_NAMES

logger = logging.getLogger(__name__)

DEVIL_SQUARE = 9
SPAWN_MAPS = set(MAP_NAMES) - {DEVIL_SQUARE}  # Devil Square's monsters come with its event (roadmap M7)
SINGLE_SPREAD = 3  # a single monster appears within this many tiles of its spot, mup's choice
# MonsterSetBase sections: 0 NPCs and traps, 1 monsters in an area, 2 single monsters, 3 and 4 events
AREA, SINGLE = 1, 2


def load_info(path):
    """Monster type -> MonsterInfo."""
    info = {}
    with open(path, encoding='latin-1') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('//') or line == 'end':
                continue
            v = shlex.split(line)
            n = int(v[0])
            info[n] = MonsterInfo(
                number=n, name=v[2], level=int(v[3]), life=int(v[4]), damage_min=int(v[6]), damage_max=int(v[7]),
                defense=int(v[8]), attack_rate=int(v[10]), defense_rate=int(v[11]), move_range=int(v[12]),
                attack_range=int(v[14]), view_range=int(v[15]), move_speed=int(v[16]), attack_speed=int(v[17]),
                regen_time=int(v[18]), item_rate=int(v[20]), money_rate=int(v[21]), max_item_level=int(v[22]))
    return info


def load_spawns(path, info):
    """Monster spawns on the maps of SPAWN_MAPS: the area and single monster sections."""
    spawns = []
    section = None
    unknown = Counter()
    with open(path, encoding='latin-1') as f:
        for line in f:
            v = line.split('//', 1)[0].split()
            if not v:
                continue
            if v[0] == 'end':
                section = None
                continue
            if section is None:
                section = int(v[0])
                continue
            if section not in (AREA, SINGLE):
                continue

            number, map_id, leash = int(v[0]), int(v[1]), int(v[2])
            if map_id not in SPAWN_MAPS:
                continue
            if number not in info:
                unknown[number] += 1
                continue
            if section == AREA:
                x1, y1, x2, y2, count = int(v[3]), int(v[4]), int(v[5]), int(v[6]), int(v[8])
                spawns.append(Spawn(number, map_id, range(x1, x2 + 1), range(y1, y2 + 1), leash, count))
            else:
                x, y = int(v[3]), int(v[4])
                spawns.append(Spawn(number, map_id, range(max(0, x - SINGLE_SPREAD), min(255, x + SINGLE_SPREAD) + 1),
                                    range(max(0, y - SINGLE_SPREAD), min(255, y + SINGLE_SPREAD) + 1), leash))
    if unknown:
        logger.warning('%s: spawns of unknown monster types skipped: %s', path, dict(unknown))
    return spawns


def create(spawns, info, cids, last_cid):
    """A Monster for every monster of the spawns, ids from cids up to last_cid."""
    monsters = [Monster(next(cids), info[s.number], s, map_id=s.map_id) for s in spawns for _ in range(s.count)]
    if monsters and monsters[-1].cid > last_cid:
        raise ValueError('{} monsters, the ids end at {}'.format(len(monsters), last_cid))
    return monsters


def spawn(game, mob, now):
    """Puts mob with full life on a free spot of its spawn area. False when there is none."""
    m = game.maps[mob.map_id]
    spot = m.terrain.random_spot(mob.spawn.xs, mob.spawn.ys, m.monster_can_stand)
    if spot is None:
        return False
    mob.x, mob.y = mob.home = spot
    mob.life = mob.max_life
    mob.dead = False
    mob.target = None
    mob.damage_by = {}
    mob.returning = False
    mob.path = []
    mob.respawn_at = None
    mob.next_think_at = mob.next_attack_at = mob.next_step_at = now
    m.add_monster(mob)
    view.monster_appeared(game, mob)
    return True


def kill(game, mob, now):
    """mob died: it stays in view as a corpse until it respawns."""
    mob.dead = True
    mob.life = 0
    mob.effects.clear()
    mob.state = 0
    mob.target = None
    mob.path = []
    mob.respawn_at = now + mob.info.regen_time
    game.maps[mob.map_id].remove_monster(mob)
    game.dead_monsters.add(mob)


def respawn(game, mob, now):
    view.monster_removed(game, mob)
    if spawn(game, mob, now):
        game.dead_monsters.discard(mob)
    else:
        mob.respawn_at = now + mob.info.regen_time
