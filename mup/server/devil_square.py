"""
Devil Square (map 9), see Devil Square in docs/protocol-097.md. Rounds start at the configured times; for
devil_square_entry seconds before one, Charon (237) in Noria opens his window (30 4) and lets players into one of
4 squares by level (90) for a Devil's invitation (14/19) of the square's level. During the round the square's
monsters (the later server's map 9 areas, left out of the world) are out, a kill scores the monster's level. At the
end each square's players are ranked (93) with exp and zen by rank, and go back to Noria a moment later. The client's
92 counts down the last 30 s of the entry and of the round, 91 tells how long until Charon lets players in.
"""
import datetime
import logging
import math
import random
import time
from dataclasses import dataclass, field
from itertools import count
from typing import Dict, List
from mup.model.item import GRID
from mup.packet.server import (SAnnouncement, SDevilSquareCountdown, SDevilSquareRanking, SDevilSquareResult,
                               SDevilSquareTime, SItemDeleted, SMapMove, SRespawn, STalk)
from mup.server import experience, monster, view
from mup.server.character import NORIA
from mup.server.ground import MAX_ZEN
from mup.server.shop import DEVILS_EYE, DEVILS_KEY, DEVILS_INVITATION

logger = logging.getLogger(__name__)

CHARON = 237
MAP = monster.DEVIL_SQUARE
GATES = (58, 59, 60, 61)  # where each square's players arrive (the client's Gate.bmd)
LEVELS = ((10, 99), (100, 179), (180, 249), (250, 0xFFFF))  # each square's, the client's (0x4fcf4c)
INVITATION_TILE = 24  # 90 [4] is the invitation's grid tile + this
MAX_PLAYERS = 10  # per square, mup's choice (the client has "Devil Square is full")
NOTICE = 30.0  # seconds the client's 92 counts down
RANKED = 9  # ranks 93 shows besides the player's own
# exp and zen by square and rank 1..10: the later server's DevilSquare.dat
REWARD_EXP = (
    (6000, 4000, 4000, 2000, 2000, 2000, 1000, 1000, 1000, 1000),
    (8000, 6000, 6000, 4000, 4000, 4000, 2000, 2000, 2000, 2000),
    (10000, 8000, 8000, 6000, 6000, 6000, 4000, 4000, 4000, 4000),
    (20000, 10000, 10000, 8000, 8000, 8000, 6000, 6000, 6000, 6000),
)
REWARD_ZEN = (
    (30000, 25000, 25000, 20000, 20000, 20000, 15000, 15000, 15000, 15000),
    (40000, 35000, 35000, 30000, 30000, 30000, 25000, 25000, 25000, 25000),
    (50000, 45000, 45000, 40000, 40000, 40000, 35000, 35000, 35000, 35000),
    (60000, 55000, 55000, 50000, 50000, 50000, 45000, 45000, 45000, 45000),
)
# Devil's eyes and keys: the level a monster's drops have by its level, and the chance per kill (times the drop
# rate). mup's choice: each level drops where players of its square hunt
DROP_LEVELS = ((range(15, 40), 1), (range(40, 60), 2), (range(60, 80), 3), (range(80, 0x10000), 4))
DROP_CHANCE = 0.005
CLOSED, OPEN, RUNNING, ENDED = 'closed', 'open', 'running', 'ended'
OPENED = 'The gate of Devil Square is open, Charon in Noria lets you in.'  # notices (0D), mup's words


@dataclass(eq=False)
class Entry:
    """A player in a round: its square, points, the order it came in (ties rank by it)."""
    square: int
    order: int
    points: int = 0
    exp: int = 0
    zen: int = 0


@dataclass(eq=False)
class DevilSquare:
    """The event's state, times are the game clock."""
    state: str = CLOSED
    open_at: float = 0.0
    start_at: float = 0.0
    end_at: float = 0.0
    leave_at: float = 0.0
    told: set = field(default_factory=set)  # the countdowns sent this round
    players: Dict[object, Entry] = field(default_factory=dict)  # connection -> Entry
    monsters: Dict[int, List[object]] = field(default_factory=dict)  # square -> its Monsters
    order: object = field(default_factory=count)


def times(config):
    """The start times of day of the config, (hour, minute)."""
    found = []
    for t in config.devil_square_times.split():
        hour, minute = t.split(':')
        found.append((int(hour), int(minute)))
    return sorted(found)


def next_start(config, after):
    """The wall clock time (seconds) of the first round starting after the wall clock time after, None without
    times."""
    starts = times(config)
    if not starts:
        return None
    day = datetime.datetime.fromtimestamp(after).replace(hour=0, minute=0, second=0, microsecond=0)
    for days in range(2):
        for hour, minute in starts:
            at = (day + datetime.timedelta(days=days, hours=hour, minutes=minute)).timestamp()
            if at > after:
                return at
    return None


def create(game, spawns, ids, last_cid):
    """The event and its monsters (not spawned until a round starts): each spawn of map 9 belongs to the square
    whose arrival gate its area overlaps."""
    ds = DevilSquare()
    for square, number in enumerate(GATES):
        g = game.gates[number]
        mine = [s for s in spawns if overlap(s.xs, g.xs) and overlap(s.ys, g.ys)]
        ds.monsters[square] = monster.create(mine, game.monster_info, ids, last_cid)
        for mob in ds.monsters[square]:
            game.monsters[mob.cid] = mob
    logger.info('Devil Square: %s monsters in %s squares', sum(len(m) for m in ds.monsters.values()), len(GATES))
    schedule(game, ds, game.now)
    return ds


def overlap(a, b):
    return a.start < b.stop and b.start < a.stop


def schedule(game, ds, now):
    """The next round by the configured times: Charon lets players in from its start - devil_square_entry."""
    start = next_start(game.config, time.time())
    ds.state = CLOSED
    ds.told = set()
    ds.players = {}
    if start is None:
        ds.open_at = ds.start_at = math.inf
        return
    ds.start_at = now + start - time.time()
    ds.open_at = ds.start_at - game.config.devil_square_entry
    ds.end_at = ds.start_at + game.config.devil_square_length
    logger.info('Devil Square: next round at %s', datetime.datetime.fromtimestamp(start).strftime('%H:%M'))


def start_now(game):
    """GM /ds: Charon lets players in now, the round starts after devil_square_entry. False during a round."""
    ds = game.devil_square
    if ds.state != CLOSED:
        return False
    now = game.now
    ds.open_at = now
    ds.start_at = now + game.config.devil_square_entry
    ds.end_at = ds.start_at + game.config.devil_square_length
    tick(game, now)
    return True


def tick(game, now):
    """The game tick: the entry opens, the countdowns, the round starts and ends, everyone leaves."""
    ds = game.devil_square
    if ds.state == CLOSED and now >= ds.open_at:
        ds.state = OPEN
        logger.info('Devil Square: Charon lets players in')
        announce(game, OPENED)
    if ds.state == OPEN:
        if now >= ds.start_at - NOTICE and SDevilSquareCountdown.STARTS not in ds.told:
            ds.told.add(SDevilSquareCountdown.STARTS)
            for c in game.playing():
                kind = SDevilSquareCountdown.STARTS if inside(c) else SDevilSquareCountdown.ENTRY_CLOSES
                c.write(SDevilSquareCountdown(kind=kind))
        if now >= ds.start_at:
            start(game, ds, now)
    if ds.state == RUNNING:
        if now >= ds.end_at - NOTICE and SDevilSquareCountdown.ENDS not in ds.told:
            ds.told.add(SDevilSquareCountdown.ENDS)
            for c in participants(game, ds):
                c.write(SDevilSquareCountdown(kind=SDevilSquareCountdown.ENDS))
        if now >= ds.end_at:
            end(game, ds, now)
    if ds.state == ENDED and now >= ds.leave_at:
        for c in [c for c in game.playing() if c.player.map_id == MAP and not c.player.dead]:
            leave(game, c)  # the dead respawn in Noria
        schedule(game, ds, now)


def announce(game, message):
    packet = SAnnouncement(message=message)
    for c in game.playing():
        c.write(packet)


def inside(c):
    return c.player is not None and c.playing and c.player.map_id == MAP


def participants(game, ds, square=None):
    """The connections of the round's players still in Devil Square, of a square or all."""
    return [c for c, e in ds.players.items() if inside(c) and (square is None or e.square == square)]


def start(game, ds, now):
    """The round starts: the squares' monsters come out."""
    ds.state = RUNNING
    spawned = 0
    for square, mobs in ds.monsters.items():
        for mob in mobs:
            spawned += monster.spawn(game, mob, now)
    logger.info('Devil Square: the round starts with %s players, %s monsters', len(participants(game, ds)), spawned)


def end(game, ds, now):
    """The round ends: the monsters go, each square's players are ranked by points and get exp and zen by rank
    (those with points), the ranking (93) shows."""
    for mobs in ds.monsters.values():
        for mob in mobs:
            remove(game, mob)
    ds.state = ENDED
    ds.leave_at = now + game.config.devil_square_close
    for square in range(len(GATES)):
        ranked = sorted(((c, ds.players[c]) for c in participants(game, ds, square)),
                        key=lambda ce: (-ce[1].points, ce[1].order))
        for rank, (c, e) in enumerate(ranked):
            if e.points > 0 and rank < len(REWARD_EXP[square]):
                e.exp = int(REWARD_EXP[square][rank] * game.config.exp_rate)
                e.zen = REWARD_ZEN[square][rank]
        top = [row(c, e) for c, e in ranked[:RANKED]]
        for rank, (c, e) in enumerate(ranked, 1):
            p = c.player
            logger.info('Devil Square: %s ranks %s in square %s with %s points: %s exp, %s zen', p.name, rank,
                        square + 1, e.points, e.exp, e.zen)
            experience.add(game, c, e.exp)
            p.zen = min(MAX_ZEN, p.zen + e.zen)
            c.write(SDevilSquareRanking(rank=rank, entries=[row(c, e)] + top))


def row(c, e):
    return {'name': c.player.name, 'points': e.points, 'exp': e.exp, 'zen': e.zen}


def remove(game, mob):
    """An event monster leaves the map, alive or as a corpse waiting to respawn."""
    if not mob.dead:
        game.maps[mob.map_id].remove_monster(mob)
        mob.dead = True
    mob.effects.clear()
    mob.state = 0
    game.affected.discard(mob)
    game.dead_monsters.discard(mob)
    view.monster_removed(game, mob)


def leave(game, c):
    """c's player goes back to Noria, its client learns its exp and money there (F3 04)."""
    map_id, x, y = game.gate_spot(NORIA)
    game.relocate(c, map_id, x, y, 0, SRespawn.of)


def minutes_to_open(game, ds, now):
    """Minutes until Charon lets players in again, at least 1."""
    open_at = ds.open_at
    if ds.state != CLOSED:
        start = next_start(game.config, time.time() + (ds.start_at - now) + 1)
        open_at = math.inf if start is None else now + start - time.time() - game.config.devil_square_entry
    if open_at == math.inf:
        return 0xFF
    return max(1, min(0xFF, math.ceil((open_at - now) / 60)))


def talk(game, c):
    """c's player talks to Charon: his window (30 4) while he lets players in, else when he will (91)."""
    ds = game.devil_square
    if ds.state == OPEN:
        c.write(STalk(window=STalk.DEVIL_SQUARE))
        return True
    c.write(SDevilSquareTime(minutes=minutes_to_open(game, ds, game.now)))
    return False


def level(p):
    """The level the squares take: the client's, magic gladiators count 1.5 times theirs."""
    if p.class_type.value >> 5 == 3:
        return (p.level + 1) // 2 * 3
    return p.level


def enter(game, c, square, slot_byte):
    """90: c's player enters a square with the invitation in its grid tile slot_byte - 24: answered with 90, then it
    is moved to the square."""
    ds = game.devil_square
    p = c.player
    if not 0 <= square < len(GATES):
        return False
    w = c.window
    slot = slot_byte - INVITATION_TILE + GRID
    item = p.inventory.get(slot) if slot >= GRID else None
    low, high = LEVELS[square]
    if ds.state != OPEN or w is None or w.kind != STalk.DEVIL_SQUARE or p.dead or c.trade is not None:
        result = SDevilSquareResult.CLOSED
    elif level(p) > high:
        result = SDevilSquareResult.TOO_STRONG
    elif level(p) < low:
        result = SDevilSquareResult.TOO_WEAK
    elif item is None or item.type != DEVILS_INVITATION or item.level not in (0, square + 1):
        result = SDevilSquareResult.NO_INVITATION
    elif len(participants(game, ds, square)) >= MAX_PLAYERS:
        result = SDevilSquareResult.FULL
    else:
        del p.inventory[slot]
        c.write(SItemDeleted(slot=slot, unlock=0))
        c.write(SDevilSquareResult(result=SDevilSquareResult.ENTERED))
        ds.players[c] = Entry(square, next(ds.order))
        logger.info('%s enters Devil Square %s', p.name, square + 1)
        map_id, x, y = game.gate_spot(GATES[square])
        game.relocate(c, map_id, x, y, p.direction, lambda p: SMapMove(map=p.map_id, x=p.x, y=p.y,
                                                                       direction=p.direction))
        return True
    logger.debug('%s can\'t enter Devil Square %s: %s', p.name, square + 1, result)
    c.write(SDevilSquareResult(result=result))
    return False


def killed(game, c, mob):
    """c's player killed mob: in a round, a monster of Devil Square scores its level."""
    ds = game.devil_square
    e = ds.players.get(c)
    if ds.state == RUNNING and e is not None and mob.map_id == MAP and inside(c):
        e.points += mob.info.level


def loot(game, mob, rng=random):
    """A Devil's eye or key a monster may drop besides its loot, of the level its own gives."""
    if mob.map_id == MAP:
        return []
    level = next((lv for levels, lv in DROP_LEVELS if mob.info.level in levels), None)
    if level is None or rng.random() >= DROP_CHANCE * game.config.drop_rate:
        return []
    return [game.new_item(game.item_info[rng.choice((DEVILS_EYE, DEVILS_KEY))], level=level)]
