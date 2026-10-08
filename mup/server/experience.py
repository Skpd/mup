"""
Experience: what a kill is worth, levelling up, the loss on death. Player.exp is the total, as the client keeps it
(F3 03 and F3 04 carry it, 16 adds to it, F3 05 makes the client compute the next level's exp itself).
"""
import logging
import random
from mup.model.player import MAX_LEVEL, level_exp
from mup.packet.server import SExp, SLevelUp
from mup.server import stats

logger = logging.getLogger(__name__)

DEATH_LEVEL = 10  # dying loses exp from this level on
DEATH_LOSS = 0.02  # of the exp between the level and the next, usual 0.97 value
EXP_PACKET_MAX = 0xFFFF  # 16 carries 2 bytes of exp


def monster_exp(player_level, monster_level, rate, rng=random):
    """Exp for a monster of monster_level killed alone, the usual 0.97 formula: (level + 25) * level / 3, less for
    monsters more than 10 levels above the player, more from level 65, + up to a half at random."""
    exp = (monster_level + 25) * monster_level / 3
    if player_level + 10 < monster_level:
        exp = exp * (player_level + 10) / monster_level
    if monster_level >= 65:
        exp += (monster_level - 64) * (monster_level // 4)
    half = int(exp / 2)
    if half >= 1:
        exp += rng.randrange(half)
    return int(exp * rate)


def kill_shares(mob):
    """Connection -> share of the exp for the players who damaged mob: life taken / its life, at most all of it."""
    taken = sum(mob.damage_by.values())
    whole = max(mob.max_life, taken, 1)
    return {c: dmg / whole for c, dmg in mob.damage_by.items() if dmg > 0}


def reward_kill(game, mob, killer, damage, magic):
    """
    mob died, killer's hit of damage did it: everyone who damaged it and is still around gets its share of the exp
    with 16 (shown with the last hit's damage) instead of a damage packet. 16 also tells the client the monster died.
    The killer's hero swings at it unless it was magic (cid bit 15). Connections that got 16 are returned.
    """
    got = []
    for c, share in kill_shares(mob).items():
        p = c.player
        if p is None or p.dead or p.map_id != mob.map_id or not c.connected:
            continue
        exp = int(monster_exp(p.level, mob.info.level, game.config.exp_rate) * share)
        gain(game, c, exp, mob.cid, damage, quiet=magic or c is not killer)
        got.append(c)
    mob.damage_by = {}
    return got


def gain(game, c, exp, killed, damage, quiet=False):
    """
    c's player gets exp for killing killed (cid): 16 packets of at most 65535 each, the first with the damage, then
    the level ups. quiet: the hero doesn't swing (16 cid bit 15).
    """
    p = c.player
    exp = max(0, min(exp, level_exp(MAX_LEVEL) - p.exp))
    p.exp += exp
    first = True
    while first or exp > 0:
        part = min(exp, EXP_PACKET_MAX)
        c.write(SExp.of(killed | (0x8000 if quiet or not first else 0), part, damage if first else 0))
        exp -= part
        first = False

    levels = 0
    while p.level < MAX_LEVEL and p.exp >= p.next_exp:
        p.level += 1
        levels += 1
    if levels:
        p.free_points += levels * p.class_info.level_points
        stats.update(c, notify=False)  # F3 05 carries the new maximum life and mana
        p.life = p.max_life
        p.mana = p.max_mana
        logger.info('%s reached level %s', p.name, p.level)
        c.write(SLevelUp(level=p.level, points=p.free_points, max_life=p.max_life, max_mana=p.max_mana))
        game.save(c)


def death_loss(p):
    """Exp lost on death: a part of the level's exp from DEATH_LEVEL on, never below the level's start."""
    if p.level < DEATH_LEVEL:
        return
    start = level_exp(p.level)
    p.exp = max(start, p.exp - int((p.next_exp - start) * DEATH_LOSS))
