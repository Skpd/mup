import logging
from mup.model.monster import Monster
from mup.packet.server import SDamage, SAnnouncement, SKill, SExp, SLevelUp, SLife, SMana, SRespawn
from mup.server import ground, loot, monster, view
from mup.server.character import respawn_gate

logger = logging.getLogger(__name__)

RESPAWN_DELAY = 3.0  # seconds a dead player lies before it comes back in town
REGEN_INTERVAL = 3.0  # seconds between life and mana regeneration
LIFE_REGEN = 0.01  # of the maximum per interval, at least 1. mup's own rates
MANA_REGEN = 0.03
EXP_LOSS_LEVEL = 10  # dying loses exp from this level on
EXP_LOSS = 0.02  # of the exp of the level, usual 0.97 value


def hit_monster(proto, mob: Monster, dmg, flags=0):
    """Damage from proto's player to a monster, with kill, exp, level up and loot. flags: SDamage colour flags."""
    game = proto.server
    p = proto.player
    nearby = view.viewers(game, mob)

    mob.life -= dmg

    if mob.life > 0:
        for c in nearby:
            c.write(SDamage.of(mob.cid, dmg, flags))
        return

    monster.kill(game, mob, game.now)

    # todo exp: mob.base * log(mob.level - proto.player.level, 5)
    exp = min(int(90 * game.config.exp_rate), p.next_exp)
    p.exp += exp
    proto.write(SAnnouncement(message='{} of {}'.format(p.exp, p.next_exp)))
    proto.write(SExp.of(mob.cid, exp, dmg))  # shows the last hit to the killer instead of the damage packet
    if p.exp >= p.next_exp:
        p.level += 1
        p.exp = 0
        p.free_points += p.class_info.level_points
        proto.write(SLevelUp(level=p.level, points=p.free_points, max_life=p.max_life, max_mana=p.max_mana))
        game.save(proto)

    for c in nearby:
        if c != proto:
            c.write(SDamage.of(mob.cid, dmg, flags))
        c.write(SKill(cid=mob.cid, killer=proto.cid))
    ground.drop_loot(game, mob.map_id, mob.x, mob.y, loot.roll(game, mob), proto)


def hit_player(game, mob: Monster, c, dmg):
    """A monster's hit on the player of connection c."""
    # todo defense and miss (roadmap M4)
    p = c.player
    p.life = max(0, p.life - dmg)
    # the client takes the damage off the life it shows, the life packet keeps both in step
    c.write(SDamage.of(c.cid, dmg))
    c.write(SLife(value=p.life))
    if p.life == 0:
        logger.info('%s was killed by %s %s', p.name, mob.info.name, mob.cid)
        kill_player(game, c, mob.cid)


def kill_player(game, c, killer):
    """The player of c died, killer: cid of who killed it."""
    p = c.player
    p.life = 0
    p.respawn_at = game.now + RESPAWN_DELAY
    if p.level >= EXP_LOSS_LEVEL:
        p.exp = max(0, p.exp - int(p.next_exp * EXP_LOSS))
    kill = SKill(cid=c.cid, killer=killer)
    c.write(kill)
    for o in view.viewers(game, c):
        o.write(kill)


def respawn(game, c):
    """A dead player comes back with full life in the town of its map."""
    p = c.player
    p.life = p.max_life
    p.mana = p.max_mana
    p.respawn_at = None
    map_id, x, y = game.gate_spot(respawn_gate(p.map_id))
    game.relocate(c, map_id, x, y, 0, SRespawn.of)


def regen(c):
    p = c.player
    if p.dead:
        return
    if p.life < p.max_life:
        p.life = min(p.max_life, p.life + max(1, int(p.max_life * LIFE_REGEN)))
        c.write(SLife(value=p.life))
    if p.mana < p.max_mana:
        p.mana = min(p.max_mana, p.mana + max(1, int(p.max_mana * MANA_REGEN)))
        c.write(SMana(value=p.mana))
